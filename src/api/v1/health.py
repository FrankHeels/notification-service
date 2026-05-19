from typing import Any

from fastapi import APIRouter, Depends, Response, status
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

import src.rabbitmq as rabbitmq
from src.database import get_db
from src.redis import get_redis

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("/")
async def health(
    response: Response,
    db: AsyncSession = Depends(get_db),
    redis_client: Redis = Depends(get_redis),
) -> dict[str, Any]:
    """Health check endpoint."""
    services = {
        "postgres": "ok",
        "redis": "ok",
        "rabbitmq": "ok",
    }
    # 1. Проверка PostgreSQL
    try:
        await db.execute(text("SELECT 1"))
    except Exception as exc:
        services["postgres"] = f"error: {str(exc)}"
    # 2. Проверка Redis
    try:
        await redis_client.ping()
    except Exception as exc:
        services["redis"] = f"error: {str(exc)}"
    # 3. Проверка RabbitMQ: проверка глобального подключения
    is_con = await rabbitmq.is_connected() 
    if not is_con:
        services["rabbitmq"] = "error"

    # 4. Объявление статуса 503, если есть проблемы с любым сервисом
    if "error" in services.values():
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "error", "services": services}

    return {"status": "ok", "services": services}
