from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.outbox_event import OutboxEvent


class OutboxRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, event_type: str, payload: dict) -> OutboxEvent:
        """Создает новую запись в таблице outbox_events."""
        new_event = OutboxEvent(event_type=event_type, payload=payload)
        self.session.add(new_event)
        await self.session.flush()  # Получаем ID новой записи
        return new_event

    async def get_pending(self, limit: int = 100) -> list[OutboxEvent]:
        """Возвращает список ожидающих публикации событий."""
        results = await self.session.execute(
            select(OutboxEvent)
            .where(OutboxEvent.published_at.is_(None))
            .order_by(OutboxEvent.created_at)
            .limit(limit)
            .with_for_update(skip_locked=True)  # блокировка строк для других транзакций
        )
        return list(results.scalars().all())

    async def mark_published(self, event: OutboxEvent, stream_id: str) -> None:
        """Отмечает событие как опубликованное,
        устанавливая stream_id и published_at."""
        event.stream_id = stream_id
        event.published_at = datetime.now(UTC)
        event.last_error = None
        await self.session.flush()

    async def mark_failed(self, event: OutboxEvent, error_message: str) -> None:
        """Отмечает событие как неудавшееся, сохраняя сообщение об ошибке."""
        event.last_error = error_message[:2000]
        await self.session.flush()
