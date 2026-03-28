import json
from unittest.mock import AsyncMock, MagicMock, call
from uuid import uuid4

import pytest
from aio_pika import DeliveryMode
from fastapi import HTTPException

from src.models.user_channel import ChannelType
from src.schemas.notification import NotificationCreate
from src.services.notification_service import IDEMPOTENCY_TTL, NotificationService
from tests.factories import NotificationFactory, UserChannelFactory, UserFactory


def make_service() -> tuple[NotificationService, MagicMock, MagicMock, MagicMock]:
    """Собираю сервис с моками, чтобы unit-тесты проверяли только orchestration."""
    redis = MagicMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock()

    exchange = MagicMock()
    exchange.publish = AsyncMock()

    rate_limiter = MagicMock()
    rate_limiter.check_limit = AsyncMock()

    service = NotificationService(MagicMock(), redis, exchange, rate_limiter)

    # Репозитории тоже подменяю моками:
    # здесь меня интересует сценарий сервиса, а не SQL.
    service.notification_repo = MagicMock()
    service.notification_repo.get = AsyncMock()
    service.notification_repo.create = AsyncMock()
    service.notification_repo.create_delivery_log = AsyncMock()
    service.notification_repo.get_with_deliveries = AsyncMock()
    service.notification_repo.get_list_by_user = AsyncMock()

    service.user_repo = MagicMock()
    service.user_repo.get_user_channels = AsyncMock()

    return service, redis, exchange, rate_limiter


class TestSendNotification:
    """Проверяю основной use case отправки уведомления."""

    async def test_returns_cached_notification_when_idempotency_key_exists(self):
        """Если ключ уже есть в Redis, сервис должен вернуть старый notification."""
        user = UserFactory(id=uuid4())
        notification = NotificationFactory(user_id=user.id, id=uuid4())
        data = NotificationCreate(
            user_id=user.id,
            idempotency_key="same-request",
            title="Status update",
            body="Your notification already exists",
        )

        service, redis, _, rate_limiter = make_service()
        redis.get.return_value = str(notification.id)
        service.notification_repo.get.return_value = notification

        result = await service.send_notification(data)

        assert result == notification
        rate_limiter.check_limit.assert_awaited_once_with(user.id)
        service.notification_repo.get.assert_awaited_once_with(notification.id)
        service.notification_repo.create.assert_not_awaited()
        service.notification_repo.create_delivery_log.assert_not_awaited()
        service.user_repo.get_user_channels.assert_not_awaited()
        redis.set.assert_not_awaited()

    async def test_creates_logs_and_publishes_for_each_enabled_channel(self):
        """Новый запрос должен создать delivery_log и сообщение для каждого канала."""
        user = UserFactory(id=uuid4())
        channels = [
            UserChannelFactory(user_id=user.id, channel=ChannelType.EMAIL),
            UserChannelFactory(user_id=user.id, channel=ChannelType.TELEGRAM),
        ]
        data = NotificationCreate(
            user_id=user.id,
            idempotency_key="new-request",
            title="New message",
            body="You have a new message",
        )

        service, redis, _, rate_limiter = make_service()
        created_notification_id = uuid4()

        async def create_notification(notification):
            # Имитирую поведение ORM после flush: запись создана и получила id.
            notification.id = created_notification_id
            return notification

        service.notification_repo.create.side_effect = create_notification
        service.user_repo.get_user_channels.return_value = channels
        service._publish_to_channel = AsyncMock()

        result = await service.send_notification(data)

        assert result.id == created_notification_id
        assert result.user_id == user.id
        rate_limiter.check_limit.assert_awaited_once_with(user.id)
        service.notification_repo.create.assert_awaited_once()
        service.user_repo.get_user_channels.assert_awaited_once_with(user.id)
        assert service.notification_repo.create_delivery_log.await_count == 2

        created_logs = [
            repo_call.args[0]
            for repo_call in (
                service.notification_repo.create_delivery_log.await_args_list
            )
        ]
        assert [log.channel for log in created_logs] == [
            ChannelType.EMAIL,
            ChannelType.TELEGRAM,
        ]
        assert all(
            log.notification_id == created_notification_id for log in created_logs
        )

        assert service._publish_to_channel.await_args_list == [
            call(
                routing_key="email",
                payload={"notification_id": str(created_notification_id)},
            ),
            call(
                routing_key="telegram",
                payload={"notification_id": str(created_notification_id)},
            ),
        ]
        redis.set.assert_awaited_once_with(
            "idempotency:new-request",
            str(created_notification_id),
            ex=IDEMPOTENCY_TTL,
        )

    async def test_stops_before_idempotency_when_rate_limit_is_exceeded(self):
        """Если лимит исчерпан, сервис не должен доходить до idempotency и БД."""
        user = UserFactory(id=uuid4())
        data = NotificationCreate(
            user_id=user.id,
            idempotency_key="blocked-request",
            title="Too many requests",
            body="Rate limiter should stop this flow",
        )

        service, redis, _, rate_limiter = make_service()
        rate_limiter.check_limit.side_effect = HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
        )

        with pytest.raises(HTTPException) as exc_info:
            await service.send_notification(data)

        assert exc_info.value.status_code == 429
        rate_limiter.check_limit.assert_awaited_once_with(user.id)
        redis.get.assert_not_awaited()
        service.notification_repo.create.assert_not_awaited()
        service.notification_repo.create_delivery_log.assert_not_awaited()
        service.user_repo.get_user_channels.assert_not_awaited()


class TestPublishToChannel:
    """Проверяю упаковку payload перед отправкой в RabbitMQ."""

    async def test_serializes_payload_and_uses_persistent_messages(self):
        """Сервис должен сериализовать JSON и выставить persistent delivery mode."""
        service, _, exchange, _ = make_service()
        payload = {"notification_id": str(uuid4())}

        await service._publish_to_channel("email", payload)

        exchange.publish.assert_awaited_once()
        message = exchange.publish.await_args.args[0]

        assert json.loads(message.body.decode()) == payload
        assert message.delivery_mode == DeliveryMode.PERSISTENT
        assert exchange.publish.await_args.kwargs == {"routing_key": "email"}


class TestGetNotification:
    """Проверяю чтение одного уведомления через сервис."""

    async def test_success(self):
        """Если repo нашло notification, сервис должен вернуть его как есть."""
        user = UserFactory(id=uuid4())
        notification = NotificationFactory(user_id=user.id, id=uuid4())
        service, _, _, _ = make_service()
        service.notification_repo.get_with_deliveries.return_value = notification

        result = await service.get_notification(notification.id)

        assert result == notification
        service.notification_repo.get_with_deliveries.assert_awaited_once_with(
            notification.id
        )

    async def test_not_found(self):
        """Если notification нет, сервис должен превратить это в 404."""
        service, _, _, _ = make_service()
        service.notification_repo.get_with_deliveries.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await service.get_notification(uuid4())

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "Notification not found"


class TestGetUserNotifications:
    """Проверяю выдачу списка уведомлений пользователя."""

    async def test_delegates_to_repository(self):
        """Здесь сервис только передает параметры в repo без своей логики."""
        user = UserFactory(id=uuid4())
        notifications = [
            NotificationFactory(user_id=user.id, id=uuid4()),
            NotificationFactory(user_id=user.id, id=uuid4()),
        ]
        service, _, _, _ = make_service()
        service.notification_repo.get_list_by_user.return_value = notifications

        result = await service.get_user_notifications(user.id, skip=5, limit=10)

        assert result == notifications
        service.notification_repo.get_list_by_user.assert_awaited_once_with(
            user.id,
            5,
            10,
        )
