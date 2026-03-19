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