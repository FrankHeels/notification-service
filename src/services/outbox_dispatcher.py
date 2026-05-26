import asyncio
import json

import structlog
from redis.asyncio import Redis

from src.database import AsyncSessionFactory
from src.models.outbox_event import OutboxEvent
from src.repositories.outbox_repo import OutboxRepository
from src.services.public_stream import PUBLIC_EVENTS_STREAM

logger = structlog.get_logger()


class OutboxDispatcher:
    def __init__(
        self,
        redis_client: Redis,
        batch_size: int = 100,
        poll_interval: float = 1.0,
    ):
        self.redis = redis_client
        self.batch_size = batch_size
        self.poll_interval = poll_interval

    async def run_forever(self) -> int:
        while True:
            published_count = await self._dispatch_once()
            if published_count == 0:
                await asyncio.sleep(self.poll_interval)

    async def _dispatch_once(self) -> int:
        async with AsyncSessionFactory() as session:
            repo = OutboxRepository(session)
            events = await repo.get_pending(limit=self.batch_size)

            published_count = 0
            for event in events:
                try:
                    stream_id = await self._publish(event)
                except Exception as e:
                    await repo.mark_failed(event, str(e))
                    # Сохраняем статус неудачи для текущего события
                    await session.commit() 
                    logger.error(
                        "Failed to publish outbox event",
                        outbox_event_id=event.id,
                        event_type=event.event_type,
                        error=str(e),
                    )
                    # Прерываем цикл при первой же ошибке публикации
                    return published_count  

                await repo.mark_published(event, stream_id)
                published_count += 1
            # Сохраняем статус опубликованных событий
            await session.commit()  
            return published_count

    async def _publish(self, event: OutboxEvent) -> str:
        stream_id = await self.redis.xadd(
            PUBLIC_EVENTS_STREAM, # key
            {
                "event_type": event.event_type,
                "payload": json.dumps(
                    event.payload,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            },
        )
        return str(stream_id)
