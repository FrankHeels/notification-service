import asyncio
from contextlib import suppress

import redis.asyncio as redis

from src.redis import redis_pool
from src.services.outbox_dispatcher import OutboxDispatcher


async def main() -> None:
    redis_client = redis.Redis(connection_pool=redis_pool)
    dispatcher = OutboxDispatcher(redis_client)

    try:
        await dispatcher.run_forever()
    except asyncio.CancelledError:
        pass
    finally:
        with suppress(Exception):
            await redis_client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
