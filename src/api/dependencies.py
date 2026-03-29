from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from src.exceptions import (
    InvalidTokenError,
    AuthenticatedUserNotFoundError,
    AuthenticationRequiredError
)
from src.config import settings
from src.database import get_db
from src.models.user import User
from src.rabbitmq import get_exchange
from src.redis import get_redis
from src.repositories.user_repo import UserRepository
from src.services.notification_service import NotificationService
from src.services.rate_limiter import RateLimiter
from src.services.user_service import UserService

security = HTTPBearer(auto_error=False)

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    if credentials is None:
        raise AuthenticationRequiredError()
    token = credentials.credentials
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.PyJWTError:
        raise InvalidTokenError()
    
    sub = payload.get("sub")
    if not sub:
        raise InvalidTokenError()
    
    try:
        user_id = UUID(sub)
    except ValueError:
        raise InvalidTokenError()
    
    user = await db.get(User, user_id)
    if not user or user.is_active is False:
        raise AuthenticatedUserNotFoundError()
    
    return user

async def get_user_service(
    db: AsyncSession = Depends(get_db)
) -> UserService:
    repo = UserRepository(db)
    return UserService(repo)


async def get_rate_limiter(
    redis_client = Depends(get_redis)
) -> RateLimiter:
    return RateLimiter(
        redis_client=redis_client,
        max_requests=settings.rate_limit_requests,
        window_seconds=settings.rate_limit_window_seconds,
    )

async def get_notification_service(
    db: AsyncSession = Depends(get_db),
    redis_client = Depends(get_redis),
    exchange = Depends(get_exchange),
    rate_limiter: RateLimiter = Depends(get_rate_limiter),
) -> NotificationService:
    return NotificationService(db, redis_client, exchange, rate_limiter)
    
