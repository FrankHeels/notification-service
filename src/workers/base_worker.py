import asyncio
import json
from abc import ABC, abstractmethod
from uuid import UUID

import structlog
from aio_pika.abc import AbstractIncomingMessage
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import AsyncSessionFactory
from src.models.delivery_log import DeliveryStatus
from src.models.user import User
from src.models.user_channel import ChannelType
from src.providers.base import BaseNotificationProvider, NotificationPayload
from src.repositories.notification_repo import NotificationRepository
from src.repositories.outbox_repo import OutboxRepository
from src.repositories.user_repo import UserRepository
from src.services.public_events import build_delivery_updated_event

logger = structlog.get_logger()

MAX_ATTEMPTS = 3


class BaseWorker(ABC):
    """Base RabbitMQ worker with shared delivery flow."""

    channel_type: ChannelType

    def __init__(self, provider: BaseNotificationProvider) -> None:
        self.provider = provider

    async def close(self) -> None:
        await self.provider.close()

    @abstractmethod
    def get_recipient(self, user: User) -> str:
        """Return the channel-specific recipient value for a user."""
        ...

    async def process(self, message: AbstractIncomingMessage) -> None:
        logger.info(
            "Worker received message",
            channel=self.channel_type.value,
            body=message.body.decode(),
        )
        async with message.process(ignore_processed=True):
            async with AsyncSessionFactory() as session:
                retry_delay = await self._handle(message, session)
                await session.commit()

            if retry_delay is not None:
                await asyncio.sleep(retry_delay)
                await message.nack(requeue=True)

    async def _handle(
        self,
        message: AbstractIncomingMessage,
        session: AsyncSession,
    ) -> int | None:
        notification_repo = NotificationRepository(session)
        user_repo = UserRepository(session)
        outbox_repo = OutboxRepository(session)

        try:
            payload_data = json.loads(message.body)
            notification_id = UUID(payload_data["notification_id"])
        except (json.JSONDecodeError, ValueError, KeyError) as exc:
            logger.error("Invalid message format", body=message.body, error=str(exc))
            return

        # --- Решение Race Condition ---
        notification = await notification_repo.get(notification_id)
        if not notification:
            logger.warning(
                "Notification not found, retrying search...",
                notification_id=str(notification_id),
            )
            await asyncio.sleep(1.5)  # Ждем, пока база "догонит"
            notification = await notification_repo.get(notification_id)

            if not notification:
                logger.error(
                    "Notification still not found after delay. Dropping message.",
                    notification_id=str(notification_id),
                )
                return

        user = await user_repo.get(notification.user_id)
        if not user:
            logger.error("User not found", user_id=notification.user_id)
            return

        log = await notification_repo.get_delivery_log(
            notification_id, self.channel_type
        )

        if not log:
            logger.error(
                "Delivery log not found",
                notification_id=notification_id,
                channel=self.channel_type.value,
            )
            return

        if log.status in (DeliveryStatus.SENT, DeliveryStatus.FAILED):
            logger.info(
                "Delivery already finished, skipping redelivered message",
                notification_id=str(notification_id),
                channel=self.channel_type.value,
                status=log.status.value,
            )
            return

        log.attempts += 1
        try:
            payload = NotificationPayload(
                title=notification.title,
                body=notification.body,
                recipient=self.get_recipient(user),
            )
            await self.provider.send(payload)

            log.status = DeliveryStatus.SENT
            logger.info(
                "Notification sent successfully",
                notification_id=str(notification_id),
                channel=self.channel_type.value,
            )

            await self._record_delivery_event(
                outbox_repo=outbox_repo,
                notification_id=notification_id,
                username=user.username,
                status=log.status,
                attempts=log.attempts,
            )
        except Exception as exc:
            log.last_error = str(exc)
            logger.error(
                "Notification delivery failed",
                notification_id=str(notification_id),
                channel=self.channel_type.value,
                error=str(exc),
            )

            if log.attempts >= MAX_ATTEMPTS:
                log.status = DeliveryStatus.FAILED
                await self._record_delivery_event(
                    outbox_repo=outbox_repo,
                    notification_id=notification_id,
                    username=user.username,
                    status=log.status,
                    attempts=log.attempts,
                    public_reason="Delivery failed",
                )
                return

            # --- 2. Экспоненциальная задержка перед переповтором ---
            delay = log.attempts * 5
            logger.info(
                "Requeuing message with delay",
                notification_id=str(notification_id),
                delay_seconds=delay,
            )

            # Уведомляем дашборд, что мы пробуем еще раз
            await self._record_delivery_event(
                outbox_repo=outbox_repo,
                notification_id=notification_id,
                username=user.username,
                status="retrying",
                attempts=log.attempts,
                public_reason=f"Retrying in {delay} seconds",
            )

            return delay  # Возвращаем задержку, чтобы RabbitMQ перепоставил сообщение после паузы

    async def _record_delivery_event(
        self,
        outbox_repo: OutboxRepository,
        notification_id: UUID,
        username: str,
        status: DeliveryStatus | str,
        attempts: int,
        public_reason: str | None = None,
    ) -> None:
        event = build_delivery_updated_event(
            notification_id=notification_id,
            username=username,
            channel=self.channel_type,
            status=status,
            attempts=attempts,
            public_reason=public_reason,
        )
        await outbox_repo.create("delivery.updated", event)
