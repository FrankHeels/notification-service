from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import jwt
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from src.api.dependencies import get_exchange, get_rate_limiter, get_redis
from src.config import settings
from src.database import get_db
from src.main import app
from src.models.delivery_log import DeliveryLog
from src.models.notification import Notification, Priority
from src.models.user import User
from src.models.user_channel import ChannelType, UserChannel
from src.repositories.notification_repo import NotificationRepository

pytestmark = pytest.mark.asyncio(loop_scope="session")


def make_user(**kwargs) -> User:
    """Создаю пользователя с предсказуемыми тестовыми полями."""
    uid = uuid4()
    defaults = {
        "id": uid,
        "username": f"user_{uid.hex[:8]}",
        "email": f"{uid.hex[:8]}@test.com",
        "telegram_id": 123456789,
        "phone": "+79991234567",
        "is_active": True,
    }
    return User(**{**defaults, **kwargs})


def make_token(user_id: UUID) -> str:
    """Собираю реальный JWT, чтобы e2e проходил через auth-слой по-настоящему."""
    payload = {
        "sub": str(user_id),
        "iat": int(datetime.now(UTC).timestamp()),
    }
    return jwt.encode(
        payload,
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )


class FakeRedis:
    """Минимальный test double для Redis."""

    def __init__(self) -> None:
        self.storage: dict[str, str] = {}
        self.get = AsyncMock(side_effect=self._get)
        self.set = AsyncMock(side_effect=self._set)

    async def _get(self, key: str) -> str | None:
        return self.storage.get(key)

    async def _set(self, key: str, value: str, ex: int | None = None) -> None:
        self.storage[key] = value


class FakeExchange:
    """Минимальный test double для RabbitMQ exchange."""

    def __init__(self) -> None:
        self.messages: list[tuple[bytes, str]] = []
        self.publish = AsyncMock(side_effect=self._publish)

    async def _publish(self, message, routing_key: str) -> None:
        self.messages.append((message.body, routing_key))


class FakeRateLimiter:
    """Минимальный limiter, который пропускает запросы в e2e-тестах."""

    def __init__(self) -> None:
        self.check_limit = AsyncMock()


@pytest.fixture
async def fake_redis() -> FakeRedis:
    """Даю новый fake Redis на каждый тест."""
    return FakeRedis()


@pytest.fixture
async def fake_exchange() -> FakeExchange:
    """Даю новый fake exchange на каждый тест."""
    return FakeExchange()


@pytest.fixture
async def fake_rate_limiter() -> FakeRateLimiter:
    """В e2e мне не нужно тестировать Redis-алгоритм лимитера повторно."""
    return FakeRateLimiter()


@pytest.fixture
async def e2e_client(
    session,
    fake_redis: FakeRedis,
    fake_exchange: FakeExchange,
    fake_rate_limiter: FakeRateLimiter,
):
    """Собираю HTTP-клиент с реальной БД и подмененными внешними зависимостями."""

    async def override_get_db():
        yield session

    async def override_get_redis():
        return fake_redis

    async def override_get_exchange():
        return fake_exchange

    async def override_get_rate_limiter():
        return fake_rate_limiter

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_redis] = override_get_redis
    app.dependency_overrides[get_exchange] = override_get_exchange
    app.dependency_overrides[get_rate_limiter] = override_get_rate_limiter

    # Иду через ASGITransport, чтобы тестировать HTTP-flow без реального сервера.
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


class TestSendNotificationFlow:
    """Проверяю сквозной сценарий отправки уведомлений."""

    async def test_send_creates_notification_and_delivery_logs(
        self,
        session,
        e2e_client: AsyncClient,
        fake_redis: FakeRedis,
        fake_exchange: FakeExchange,
    ):
        """HTTP POST /send должен пройти весь flow до БД, Redis и exchange."""
        user = make_user()
        another_user = make_user()
        session.add_all([user, another_user])
        await session.flush()

        session.add_all(
            [
                UserChannel(
                    user_id=user.id, channel=ChannelType.EMAIL, is_enabled=True
                ),
                UserChannel(
                    user_id=user.id,
                    channel=ChannelType.TELEGRAM,
                    is_enabled=True,
                ),
            ]
        )
        await session.flush()

        token = make_token(user.id)
        response = await e2e_client.post(
            "/api/v1/notifications/send",
            headers={"Authorization": f"Bearer {token}"},
            json={
                # Специально передаю чужой user_id:
                # роут должен переписать его на current_user.id из JWT.
                "user_id": str(another_user.id),
                "idempotency_key": "e2e-send-1",
                "title": "New message",
                "body": "You have a new message",
                "priority": "high",
            },
        )

        assert response.status_code == 202
        body = response.json()
        assert body["user_id"] == str(user.id)
        assert body["idempotency_key"] == "e2e-send-1"
        assert body["priority"] == "high"

        notification_id = UUID(body["id"])
        notification = await NotificationRepository(session).get_with_deliveries(
            notification_id
        )

        assert notification is not None
        assert notification.user_id == user.id
        assert notification.priority == Priority.HIGH
        assert len(notification.deliveries) == 2
        assert {delivery.channel for delivery in notification.deliveries} == {
            ChannelType.EMAIL,
            ChannelType.TELEGRAM,
        }

        assert fake_redis.storage["idempotency:e2e-send-1"] == str(notification_id)
        assert fake_exchange.publish.await_count == 2
        assert {routing_key for _, routing_key in fake_exchange.messages} == {
            "email",
            "telegram",
        }

    async def test_send_is_idempotent_for_same_request(
        self,
        session,
        e2e_client: AsyncClient,
        fake_exchange: FakeExchange,
    ):
        """Повторный POST с тем же ключом не должен создать вторую запись."""
        user = make_user()
        session.add(user)
        await session.flush()

        session.add(UserChannel(user_id=user.id, channel=ChannelType.EMAIL))
        await session.flush()

        token = make_token(user.id)
        payload = {
            "user_id": str(user.id),
            "idempotency_key": "same-key",
            "title": "Duplicate request",
            "body": "Should not create duplicates",
            "priority": "normal",
        }

        first_response = await e2e_client.post(
            "/api/v1/notifications/send",
            headers={"Authorization": f"Bearer {token}"},
            json=payload,
        )
        second_response = await e2e_client.post(
            "/api/v1/notifications/send",
            headers={"Authorization": f"Bearer {token}"},
            json=payload,
        )

        assert first_response.status_code == 202
        assert second_response.status_code == 202
        assert first_response.json()["id"] == second_response.json()["id"]

        notification_id = UUID(first_response.json()["id"])
        delivery_logs = list(
            (
                await session.execute(
                    select(DeliveryLog).where(
                        DeliveryLog.notification_id == notification_id
                    )
                )
            ).scalars()
        )

        assert len(delivery_logs) == 1
        fake_exchange.publish.assert_awaited_once()


class TestReadNotificationFlow:
    """Проверяю чтение уведомлений через HTTP-ручки."""

    async def test_get_notification_returns_deliveries_for_owner(
        self,
        session,
        e2e_client: AsyncClient,
    ):
        """Владелец должен получить notification вместе с deliveries."""
        user = make_user()
        session.add(user)
        await session.flush()

        notification = Notification(
            id=uuid4(),
            user_id=user.id,
            idempotency_key="get-one",
            title="Stored notification",
            body="Stored body",
            priority=Priority.NORMAL,
        )
        session.add(notification)
        await session.flush()

        session.add_all(
            [
                DeliveryLog(
                    notification_id=notification.id, channel=ChannelType.EMAIL
                ),
            ]
        )
        await session.flush()

        token = make_token(user.id)
        response = await e2e_client.get(
            f"/api/v1/notifications/{notification.id}",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["id"] == str(notification.id)
        assert len(body["deliveries"]) == 1
        assert {delivery["channel"] for delivery in body["deliveries"]} == {
            "email"
        }

    async def test_get_notification_returns_403_for_foreign_user(
        self,
        session,
        e2e_client: AsyncClient,
    ):
        """Чужой пользователь не должен читать чужое уведомление."""
        owner = make_user()
        stranger = make_user()
        session.add_all([owner, stranger])
        await session.flush()

        notification = Notification(
            id=uuid4(),
            user_id=owner.id,
            idempotency_key="foreign-access",
            title="Private notification",
            body="Forbidden for other users",
        )
        session.add(notification)
        await session.flush()

        token = make_token(stranger.id)
        response = await e2e_client.get(
            f"/api/v1/notifications/{notification.id}",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 403
        assert response.json()["detail"] == "Not authorized to access this notification"

    async def test_get_notifications_returns_only_current_user_items(
        self,
        session,
        e2e_client: AsyncClient,
    ):
        """Список уведомлений должен фильтроваться по current_user из JWT."""
        user = make_user()
        another_user = make_user()
        session.add_all([user, another_user])
        await session.flush()

        notifications = [
            Notification(
                id=uuid4(),
                user_id=user.id,
                idempotency_key=f"user-{index}",
                title=f"User notification {index}",
                body="Visible to owner",
            )
            for index in range(2)
        ]
        notifications.append(
            Notification(
                id=uuid4(),
                user_id=another_user.id,
                idempotency_key="other-user",
                title="Hidden notification",
                body="Should not leak",
            )
        )
        session.add_all(notifications)
        await session.flush()

        token = make_token(user.id)
        response = await e2e_client.get(
            "/api/v1/notifications/",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        body = response.json()
        assert len(body) == 2
        assert {item["user_id"] for item in body} == {str(user.id)}
