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


async def create_guest_ws_ticket() -> str:
    """Создает одноразовый тикет для гостевого WebSocket соединения."""
    ticket = str(uuid.uuid4())
    client = redis.Redis(connection_pool=redis_pool)
    try:
        await client.setex(f"guest_ws_ticket:{ticket}", 30, "guest")
        return ticket
    finally:
        await client.aclose()


async def consume_guest_ws_ticket(ticket: str) -> bool:
    """Проверяет и удаляет гостевой тикет."""
    client = redis.Redis(connection_pool=redis_pool)
    try:
        async with client.pipeline() as pipe:
            pipe.get(f"guest_ws_ticket:{ticket}")
            pipe.delete(f"guest_ws_ticket:{ticket}")
            result = await pipe.execute()

        return result[0] is not None
    finally:
        await client.aclose()
