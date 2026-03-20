import json
from uuid import UUID
from abc import ABC, abstractmethod

import structlog
from aio_pika.abc import AbstractIncomingMessage
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import AsyncSessionFactory
from src.models.delivery_log import DeliveryStatus
from src.models.user import User
from src.models.user_channel import ChannelType
from src.providers.base import BaseNotificationProvider, NotificationPayload
from src.repositories.notification_repo import NotificationRepository
from src.repositories.user_repo import UserRepository

logger = structlog.get_logger()

MAX_ATTEMPTS = 3

class BaseWorker(ABC):
    """Базовый воркер — общая логика обработки сообщений из RabbitMQ."""

    channel_type: ChannelType
    
    def __init__(self, provider: BaseNotificationProvider) -> None:
        self.provider = provider

    @abstractmethod
    def get_recipient(self, user: User) -> str:
        """Метод для получения контактных данных пользователя (email, telegram_id, phone)."""
        ...

    async def process(self, message: AbstractIncomingMessage) -> None:

        async with message.process(ignore_processed=True):
            async with AsyncSessionFactory() as session:
                await self._handle(message, session)
                await session.commit()  # Коммитим изменения в БД после обработки сообщения

    async def _handle(self, message: AbstractIncomingMessage, session: AsyncSession) -> None:
        notification_repo = NotificationRepository(session)
        user_repo = UserRepository(session)

        try:
            payload_data = json.loads(message.body)
            notification_id = UUID(payload_data["notification_id"])
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            logger.error("Invalid message format", body=message.body, error=str(e))
            return #ACK

        notification = await notification_repo.get(notification_id)
        if not notification:
            logger.error("Notification not found", notification_id=notification_id)
            return

        user = await user_repo.get(notification.user_id)
        if not user:
            logger.error("User not found", user_id=notification.user_id)
            return

        log = await notification_repo.get_delivery_log(notification_id, self.channel_type)
        if not log:
            logger.error("Delivery log not found", notification_id=notification_id, channel=self.channel_type.value)
            return

        recipient = self.get_recipient(user)

        payload = NotificationPayload(
            title=notification.title,
            body=notification.body,
            recipient=recipient
        )
        
        log.attempts += 1
        try:
            await self.provider.send(payload)
            log.status = DeliveryStatus.SENT
        except Exception as e:
            log.last_error = str(e)
            if log.attempts >= MAX_ATTEMPTS:
                log.status = DeliveryStatus.FAILED
            else:
                await message.nack(requeue=True)  # вернуть в очередь