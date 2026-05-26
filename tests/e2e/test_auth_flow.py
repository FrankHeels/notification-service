from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from src.api.dependencies import get_exchange, get_rate_limiter, get_redis
from src.config import settings
from src.database import get_db
from src.main import app
from src.models.refresh_token import RefreshToken
from src.models.user import User
from src.services.security import hash_password, hash_refresh_token

pytestmark = pytest.mark.asyncio(loop_scope="session")


class FakeRedis:
    def __init__(self) -> None:
        self.storage: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.storage.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.storage[key] = value

    async def delete(self, key: str) -> None:
        self.storage.pop(key, None)


class FakeExchange:
    def __init__(self) -> None:
        self.messages: list[tuple[bytes, str]] = []

    async def publish(self, message, routing_key: str) -> None:
        self.messages.append((message.body, routing_key))


class FakeRateLimiter:
    async def check_limit(self, user_id: UUID) -> None:
        return None


@pytest.fixture
async def auth_client(session):
    async def override_get_db():
        yield session

    async def override_get_redis():
        return FakeRedis()

    async def override_get_exchange():
        return FakeExchange()

    async def override_get_rate_limiter():
        return FakeRateLimiter()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_redis] = override_get_redis
    app.dependency_overrides[get_exchange] = override_get_exchange
    app.dependency_overrides[get_rate_limiter] = override_get_rate_limiter

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


def make_user(**kwargs) -> User:
    uid = uuid4()
    defaults = {
        "id": uid,
        "username": f"user_{uid.hex[:8]}",
        "email": f"{uid.hex[:8]}@test.com",
        "password_hash": hash_password("secret-password"),
        "is_active": True,
    }
    return User(**{**defaults, **kwargs})


async def test_register_creates_user_with_password_hash_and_returns_tokens(
    session,
    auth_client: AsyncClient,
):
    response = await auth_client.post(
        "/api/v1/auth/register",
        json={
            "username": "john_doe",
            "email": "john@example.com",
            "password": "correct horse battery staple",
            "telegram_id": 123456789,
            "phone": "+79991234567",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["user"]["username"] == "john_doe"
    assert body["user"]["email"] == "john@example.com"
    assert "password_hash" not in body["user"]
    assert body["tokens"]["access_token"]
    assert body["tokens"]["refresh_token"]
    assert body["tokens"]["token_type"] == "bearer"

    user_id = UUID(body["user"]["id"])
    user = await session.get(User, user_id)
    assert user is not None
    assert user.password_hash != "correct horse battery staple"

    refresh_hash = hash_refresh_token(body["tokens"]["refresh_token"])
    token_row = (
        await session.execute(
            select(RefreshToken).where(RefreshToken.token_hash == refresh_hash)
        )
    ).scalar_one_or_none()
    assert token_row is not None
    assert token_row.user_id == user_id
    assert token_row.revoked_at is None


async def test_login_accepts_username_or_email(session, auth_client: AsyncClient):
    user = make_user(username="login_user", email="login@example.com")
    session.add(user)
    await session.flush()

    by_username = await auth_client.post(
        "/api/v1/auth/login",
        data={"username": "login_user", "password": "secret-password"},
    )
    by_email = await auth_client.post(
        "/api/v1/auth/login",
        data={"username": "login@example.com", "password": "secret-password"},
    )

    assert by_username.status_code == 200
    assert by_email.status_code == 200
    assert by_username.json()["access_token"]
    assert by_email.json()["access_token"]


async def test_login_rejects_wrong_password_with_generic_401(
    session,
    auth_client: AsyncClient,
):
    user = make_user(username="wrong_password_user")
    session.add(user)
    await session.flush()

    response = await auth_client.post(
        "/api/v1/auth/login",
        data={"username": "wrong_password_user", "password": "bad-password"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid username or password"


async def test_refresh_rotates_refresh_token(session, auth_client: AsyncClient):
    register_response = await auth_client.post(
        "/api/v1/auth/register",
        json={
            "username": "refresh_user",
            "email": "refresh@example.com",
            "password": "correct horse battery staple",
        },
    )
    old_refresh_token = register_response.json()["tokens"]["refresh_token"]

    response = await auth_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": old_refresh_token},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["refresh_token"] != old_refresh_token

    old_row = (
        await session.execute(
            select(RefreshToken).where(
                RefreshToken.token_hash == hash_refresh_token(old_refresh_token)
            )
        )
    ).scalar_one()
    new_row = (
        await session.execute(
            select(RefreshToken).where(
                RefreshToken.token_hash == hash_refresh_token(body["refresh_token"])
            )
        )
    ).scalar_one()
    assert old_row.revoked_at is not None
    assert new_row.revoked_at is None


async def test_refresh_reuse_revokes_active_user_tokens(
    session,
    auth_client: AsyncClient,
):
    register_response = await auth_client.post(
        "/api/v1/auth/register",
        json={
            "username": "reuse_user",
            "email": "reuse@example.com",
            "password": "correct horse battery staple",
        },
    )
    old_refresh_token = register_response.json()["tokens"]["refresh_token"]
    first_refresh = await auth_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": old_refresh_token},
    )
    active_refresh_token = first_refresh.json()["refresh_token"]

    reuse_response = await auth_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": old_refresh_token},
    )

    assert reuse_response.status_code == 401
    active_row = (
        await session.execute(
            select(RefreshToken).where(
                RefreshToken.token_hash == hash_refresh_token(active_refresh_token)
            )
        )
    ).scalar_one()
    assert active_row.revoked_at is not None


async def test_logout_revokes_refresh_token(auth_client: AsyncClient):
    register_response = await auth_client.post(
        "/api/v1/auth/register",
        json={
            "username": "logout_user",
            "email": "logout@example.com",
            "password": "correct horse battery staple",
        },
    )
    refresh_token = register_response.json()["tokens"]["refresh_token"]

    logout_response = await auth_client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": refresh_token},
    )
    refresh_response = await auth_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )

    assert logout_response.status_code == 204
    assert refresh_response.status_code == 401


async def test_me_returns_current_user(auth_client: AsyncClient):
    register_response = await auth_client.post(
        "/api/v1/auth/register",
        json={
            "username": "me_user",
            "email": "me@example.com",
            "password": "correct horse battery staple",
        },
    )
    access_token = register_response.json()["tokens"]["access_token"]

    response = await auth_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 200
    assert response.json()["username"] == "me_user"
    assert "password_hash" not in response.json()


async def test_inactive_user_cannot_use_access_token(
    session,
    auth_client: AsyncClient,
):
    user = make_user(is_active=False)
    session.add(user)
    await session.flush()
    token = jwt.encode(
        {
            "sub": str(user.id),
            "type": "access",
            "iat": int(datetime.now(UTC).timestamp()),
            "exp": int((datetime.now(UTC) + timedelta(minutes=30)).timestamp()),
            "jti": "inactive-test",
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )

    response = await auth_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401
