import json
import uuid
from collections.abc import AsyncGenerator
import redis.asyncio as redis
from src.config import settings

redis_pool: redis.ConnectionPool = redis.ConnectionPool.from_url(
    str(settings.redis_url),
    max_connections=20,  # Максимальное количество соединений в пуле
    decode_responses=True,  # Декодировать байты в строки
)


async def get_redis() -> AsyncGenerator[redis.Redis, None]:

    client = redis.Redis(connection_pool=redis_pool)
    try:
        yield client
    finally:
        await client.aclose()


async def publish_event(channel: str, event: dict) -> None:
    """Публикует событие в Redis Pub/Sub."""
    client = redis.Redis(connection_pool=redis_pool)
    try:
        await client.publish(channel, json.dumps(event))
    finally:
        await client.aclose()


async def create_ws_ticket(user_id: uuid.UUID) -> str:
    """Создает одноразовый тикет для WebSocket соединения и сохраняет его в Redis с TTL."""
    ticket = str(uuid.uuid4())
    client = redis.Redis(connection_pool=redis_pool)
    try:
        await client.setex(f"ws_ticket:{ticket}", 30, str(user_id))
        return ticket
    finally:
        await client.aclose()


async def consume_ws_ticket(ticket: str) -> uuid.UUID | None:
    client = redis.Redis(connection_pool=redis_pool)
    try:
        # Используем транзакцию (pipeline) для атомарного GET + DEL
        async with client.pipeline() as pipe:
            pipe.get(f"ws_ticket:{ticket}")
            pipe.delete(f"ws_ticket:{ticket}")
            result = await pipe.execute()

        user_id_str = result[0]
        if user_id_str is None:
            return None
        return uuid.UUID(user_id_str)
    finally:
        await client.aclose()
