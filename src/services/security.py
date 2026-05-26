import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt
from pwdlib import PasswordHash

from src.config import settings

password_hasher = PasswordHash.recommended()

def hash_password(password: str) -> str:
    """Хэширует пароль с помощью bcrypt и argon2."""
    return password_hasher.hash(password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Проверяет пароль на соответствие хэшу."""
    try:
        return password_hasher.verify(plain_password, password_hash)
    except Exception:
        return False
    

def create_access_token(user_id: UUID) -> str:
    now = datetime.now(UTC)
    expires_at = now + timedelta(minutes=settings.jwt_expire_minutes)

    payload = {
        "sub": str(user_id),
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
        "jti": uuid4().hex # Уникальный идентификатор токена для возможности отзыва
    } 

    return jwt.encode(
        payload,
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )


def create_refresh_token() -> str:
    return secrets.token_urlsafe(64)


def hash_refresh_token(token: str) -> str:
    """Хэширует refresh-токен для безопасного хранения в БД."""
    return hmac.new(
        key=settings.jwt_secret.encode("utf-8"),
        msg=token.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()


def access_token_expires_in_seconds() -> int:
    return settings.jwt_expire_minutes * 60
