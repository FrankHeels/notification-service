import json
from uuid import UUID

from aio_pika import DeliveryMode, Message
from aio_pika.abc import AbstractExchange
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from src.exceptions import NotificationNotFoundError
from src.models.delivery_log import DeliveryLog
from src.models.notification import Notification
from src.repositories.notification_repo import NotificationRepository
from src.repositories.user_repo import UserRepository
from src.schemas.notification import NotificationCreate
from src.services.rate_limiter import RateLimiter

IDEMPOTENCY_TTL = 60 * 60 * 24


class NotificationService:
    def __init__(
        self,
        session: AsyncSession,
        redis_client: Redis,
        exchange: AbstractExchange,
        rate_limiter: RateLimiter,
    ) -> None:
        self.notification_repo = NotificationRepository(session)
        self.user_repo = UserRepository(session)
        self.redis = redis_client
        self.exchange = exchange
        self.rate_limiter = rate_limiter

    async def send_notification(self, data: NotificationCreate) -> Notification:
        await self.rate_limiter.check_limit(data.user_id)

        key = f"idempotency:{data.idempotency_key}"
        cached = await self.redis.get(key)
        if cached:
            notification_id = UUID(cached)
            return await self.notification_repo.get(notification_id)

        notification = Notification(
            user_id=data.user_id,
            idempotency_key=data.idempotency_key,
            title=data.title,
            body=data.body,
            priority=data.priority,
        )
        await self.notification_repo.create(notification)

        channels = await self.user_repo.get_user_channels(data.user_id)

        for channel in channels:
            log = DeliveryLog(
                notification_id=notification.id,
                channel=channel.channel,
            )
            await self.notification_repo.create_delivery_log(log)
            await self._publish_to_channel(
                routing_key=channel.channel.value,
                payload={"notification_id": str(notification.id)},
            )

        await self.redis.set(key, str(notification.id), ex=IDEMPOTENCY_TTL)
        return notification

    async def _publish_to_channel(
        self,
        routing_key: str,
        payload: dict,
    ) -> None:
        message = Message(
            body=json.dumps(payload).encode(),
            # Делаю сообщение persistent, чтобы RabbitMQ не потерял его при рестарте.
            delivery_mode=DeliveryMode.PERSISTENT,
        )
        await self.exchange.publish(message, routing_key=routing_key)

    async def get_notification(self, notification_id: UUID) -> Notification:
        notification = await self.notification_repo.get_with_deliveries(notification_id)
        if not notification:
            raise NotificationNotFoundError()
        return notification

    async def get_user_notifications(
        self,
        user_id: UUID,
        skip: int = 0,
        limit: int = 20,
    ) -> list[Notification]:
        return await self.notification_repo.get_list_by_user(user_id, skip, limit)
