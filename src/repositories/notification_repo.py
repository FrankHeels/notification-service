from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.delivery_log import DeliveryLog
from src.models.notification import Notification
from src.models.user_channel import ChannelType
from src.repositories.base import BaseRepository


class NotificationRepository(BaseRepository[Notification]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Notification, session)

    async def get_by_idempotency_key(self, ind_key: str) -> Notification | None:
        result = await self.session.execute(
            select(Notification).where(Notification.idempotency_key == ind_key)
        )
        return result.scalar_one_or_none()

    async def get_with_deliveries(self, notification_id: UUID) -> Notification | None:
        result = await self.session.execute(
            select(Notification)
            .where(Notification.id == notification_id)
            .options(selectinload(Notification.deliveries))
        )
        return result.scalar_one_or_none()

    async def get_list_by_user(
        self, user_id: UUID, skip: int = 0, limit: int = 20
    ) -> list[Notification]:
        result = await self.session.execute(
            select(Notification)
            .where(Notification.user_id == user_id)
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def create_delivery_log(self, log: DeliveryLog) -> DeliveryLog:
        self.session.add(log)
        await self.session.flush()
        return log

    async def get_delivery_log(
        self, notification_id: UUID, channel: ChannelType
    ) -> DeliveryLog | None:
        result = await self.session.execute(
            select(DeliveryLog).where(
                DeliveryLog.notification_id == notification_id,
                DeliveryLog.channel == channel,
            )
        )
        return result.scalar_one_or_none()
