import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from src.models.delivery_log import DeliveryLog, DeliveryStatus
from src.models.notification import Notification, Priority, Status
from src.models.user import User
from src.models.user_channel import ChannelType
from src.repositories.notification_repo import NotificationRepository

# Здесь тоже нужен session-scoped loop, чтобы testcontainers и asyncpg жили
# на одном event loop во всем integration-наборе.
pytestmark = pytest.mark.asyncio(loop_scope="session")


def make_user(**kwargs) -> User:
    """Создаю пользователя с уникальными полями для чистых integration-сценариев."""
    uid = uuid.uuid4()
    defaults = {
        "id": uid,
        "username": f"user_{uid.hex[:8]}",
        "email": f"{uid.hex[:8]}@test.com",
        "password_hash": "test-password-hash",
        "is_active": True,
    }
    return User(**{**defaults, **kwargs})


def make_notification(user: User, **kwargs) -> Notification:
    """Создаю notification, привязанный к конкретному пользователю."""
    uid = uuid.uuid4()
    defaults = {
        "id": uid,
        "user_id": user.id,
        "idempotency_key": f"idem-{uid.hex}",
        "title": "Test notification",
        "body": "Test body",
        "priority": Priority.NORMAL,
        "status": Status.PENDING,
    }
    return Notification(**{**defaults, **kwargs})


def make_delivery_log(
    notification: Notification,
    channel: ChannelType,
    **kwargs,
) -> DeliveryLog:
    """Создаю delivery_log для конкретного notification и канала."""
    defaults = {
        "id": uuid.uuid4(),
        "notification_id": notification.id,
        "channel": channel,
        "status": DeliveryStatus.PENDING,
        "attempts": 0,
    }
    return DeliveryLog(**{**defaults, **kwargs})


class TestGet:
    """Проверяю базовый get() по primary key."""

    async def test_success(self, session):
        """Сохраненный notification должен читаться обратно тем же repo."""
        # Сначала сохраняю user, потом notification:
        # без явного relationship SQLAlchemy не обязан угадывать порядок INSERT.
        user = make_user()
        session.add(user)
        await session.flush()

        notification = make_notification(user)
        session.add(notification)
        await session.flush()

        repo = NotificationRepository(session)
        result = await repo.get(notification.id)

        assert result is not None
        assert result.id == notification.id
        assert result.idempotency_key == notification.idempotency_key

    async def test_not_found(self, session):
        """Неизвестный notification id должен вернуть None."""
        repo = NotificationRepository(session)
        result = await repo.get(uuid.uuid4())

        assert result is None


class TestCreate:
    """Проверяю вставку notification через BaseRepository.create()."""

    async def test_success(self, session):
        """После create() объект должен сохраниться с ожидаемыми default-полями."""
        user = make_user()
        session.add(user)
        await session.flush()

        notification = make_notification(user)
        repo = NotificationRepository(session)
        result = await repo.create(notification)

        assert result.id == notification.id
        assert result.user_id == user.id
        assert result.status == Status.PENDING

    async def test_duplicate_idempotency_key_raises(self, session):
        """Уникальность idempotency_key проверяю на уровне БД."""
        user = make_user()
        session.add(user)
        await session.flush()

        key = f"same-key-{uuid.uuid4().hex}"
        n1 = make_notification(user, idempotency_key=key)
        n2 = make_notification(user, idempotency_key=key)

        repo = NotificationRepository(session)
        await repo.create(n1)

        with pytest.raises(IntegrityError):
            await repo.create(n2)


class TestGetByIdempotencyKey:
    """Проверяю поиск уведомления по idempotency key."""

    async def test_success(self, session):
        """Точный ключ должен находить ровно тот notification, который я сохранил."""
        user = make_user()
        session.add(user)
        await session.flush()

        notification = make_notification(user)
        session.add(notification)
        await session.flush()

        repo = NotificationRepository(session)
        result = await repo.get_by_idempotency_key(notification.idempotency_key)

        assert result is not None
        assert result.id == notification.id

    async def test_not_found(self, session):
        """Отсутствующий key должен вернуть пустой результат."""
        repo = NotificationRepository(session)
        result = await repo.get_by_idempotency_key("nonexistent-key")

        assert result is None

    async def test_returns_correct_notification(self, session):
        """Если notifications несколько, метод должен выбрать именно нужный объект."""
        user = make_user()
        session.add(user)
        await session.flush()

        n1 = make_notification(user)
        n2 = make_notification(user)
        session.add_all([n1, n2])
        await session.flush()

        repo = NotificationRepository(session)
        result = await repo.get_by_idempotency_key(n1.idempotency_key)

        assert result is not None
        assert result.id == n1.id
        assert result.id != n2.id


class TestGetWithDeliveries:
    """Проверяю загрузку notification вместе с delivery_log."""

    async def test_returns_notification_with_deliveries(self, session):
        """selectinload должен реально подтянуть связанные deliveries."""
        user = make_user()
        session.add(user)
        await session.flush()

        notification = make_notification(user)
        session.add(notification)
        await session.flush()

        log = make_delivery_log(notification, ChannelType.EMAIL)
        session.add(log)
        await session.flush()

        repo = NotificationRepository(session)
        result = await repo.get_with_deliveries(notification.id)

        assert result is not None
        assert result.id == notification.id
        assert len(result.deliveries) == 1
        assert result.deliveries[0].channel == ChannelType.EMAIL

    async def test_returns_all_deliveries(self, session):
        """Коллекция deliveries должна содержать все каналы, а не только первый."""
        user = make_user()
        session.add(user)
        await session.flush()

        notification = make_notification(user)
        session.add(notification)
        await session.flush()

        session.add_all(
            [
                make_delivery_log(notification, ChannelType.EMAIL),
                make_delivery_log(notification, ChannelType.TELEGRAM),
            ]
        )
        await session.flush()

        repo = NotificationRepository(session)
        result = await repo.get_with_deliveries(notification.id)

        assert result is not None
        assert len(result.deliveries) == 2

    async def test_returns_empty_deliveries_when_none(self, session):
        """Если delivery_log еще нет, deliveries должен быть пустым списком."""
        user = make_user()
        session.add(user)
        await session.flush()

        notification = make_notification(user)
        session.add(notification)
        await session.flush()

        repo = NotificationRepository(session)
        result = await repo.get_with_deliveries(notification.id)

        assert result is not None
        assert result.deliveries == []

    async def test_not_found(self, session):
        """Это отдельный сценарий: самого notification не существует вовсе."""
        repo = NotificationRepository(session)
        result = await repo.get_with_deliveries(uuid.uuid4())

        assert result is None

    async def test_deliveries_isolated_between_notifications(self, session):
        """Чужие delivery_log не должны примешиваться к другому notification."""
        user = make_user()
        session.add(user)
        await session.flush()

        n1 = make_notification(user)
        n2 = make_notification(user)
        session.add_all([n1, n2])
        await session.flush()

        session.add(make_delivery_log(n1, ChannelType.EMAIL))
        await session.flush()

        repo = NotificationRepository(session)
        result = await repo.get_with_deliveries(n2.id)

        assert result is not None
        assert result.deliveries == []


class TestGetListByUser:
    """Проверяю пагинированную выборку уведомлений пользователя."""

    async def test_returns_user_notifications(self, session):
        """Базовый list-case: repo должно вернуть все notifications конкретного user."""
        user = make_user()
        session.add(user)
        await session.flush()

        session.add_all([make_notification(user) for _ in range(3)])
        await session.flush()

        repo = NotificationRepository(session)
        result = await repo.get_list_by_user(user.id)

        assert len(result) == 3

    async def test_isolation_between_users(self, session):
        """Notifications другого пользователя не должны попадать в выборку."""
        user1 = make_user()
        user2 = make_user()
        session.add_all([user1, user2])
        await session.flush()

        session.add_all([make_notification(user1), make_notification(user1)])
        await session.flush()

        repo = NotificationRepository(session)
        result = await repo.get_list_by_user(user2.id)

        assert result == []

    async def test_skip(self, session):
        """skip должен пропускать первые записи в выборке."""
        user = make_user()
        session.add(user)
        await session.flush()

        session.add_all([make_notification(user) for _ in range(5)])
        await session.flush()

        repo = NotificationRepository(session)
        result = await repo.get_list_by_user(user.id, skip=3)

        assert len(result) == 2

    async def test_limit(self, session):
        """limit должен ограничивать размер результата."""
        user = make_user()
        session.add(user)
        await session.flush()

        session.add_all([make_notification(user) for _ in range(5)])
        await session.flush()

        repo = NotificationRepository(session)
        result = await repo.get_list_by_user(user.id, limit=2)

        assert len(result) == 2

    async def test_returns_empty_for_unknown_user(self, session):
        """Для неизвестного user_id контрактом является пустой список."""
        repo = NotificationRepository(session)
        result = await repo.get_list_by_user(uuid.uuid4())

        assert result == []


class TestCreateDeliveryLog:
    """Проверяю создание записей в delivery_log."""

    async def test_success(self, session):
        """Одна запись доставки должна сохраниться с ожидаемыми default-значениями."""
        user = make_user()
        session.add(user)
        await session.flush()

        notification = make_notification(user)
        session.add(notification)
        await session.flush()

        log = make_delivery_log(notification, ChannelType.EMAIL)
        repo = NotificationRepository(session)
        result = await repo.create_delivery_log(log)

        assert result.id == log.id
        assert result.notification_id == notification.id
        assert result.channel == ChannelType.EMAIL
        assert result.status == DeliveryStatus.PENDING
        assert result.attempts == 0

    async def test_multiple_channels_for_same_notification(self, session):
        """Один notification может иметь delivery_log сразу по нескольким каналам."""
        user = make_user()
        session.add(user)
        await session.flush()

        notification = make_notification(user)
        session.add(notification)
        await session.flush()

        repo = NotificationRepository(session)
        await repo.create_delivery_log(
            make_delivery_log(notification, ChannelType.EMAIL)
        )
        await repo.create_delivery_log(
            make_delivery_log(notification, ChannelType.TELEGRAM)
        )

        result = await repo.get_with_deliveries(notification.id)

        assert result is not None
        assert len(result.deliveries) == 2


class TestGetDeliveryLog:
    """Проверяю поиск конкретного delivery_log по notification_id и channel."""

    async def test_success(self, session):
        """Метод должен найти точную пару notification_id + channel."""
        user = make_user()
        session.add(user)
        await session.flush()

        notification = make_notification(user)
        session.add(notification)
        await session.flush()

        log = make_delivery_log(notification, ChannelType.EMAIL)
        session.add(log)
        await session.flush()

        repo = NotificationRepository(session)
        result = await repo.get_delivery_log(notification.id, ChannelType.EMAIL)

        assert result is not None
        assert result.id == log.id
        assert result.channel == ChannelType.EMAIL

    async def test_returns_correct_channel(self, session):
        """Если каналов несколько, repo должно вернуть именно запрошенный канал."""
        user = make_user()
        session.add(user)
        await session.flush()

        notification = make_notification(user)
        session.add(notification)
        await session.flush()

        email_log = make_delivery_log(notification, ChannelType.EMAIL)
        tg_log = make_delivery_log(notification, ChannelType.TELEGRAM)
        session.add_all([email_log, tg_log])
        await session.flush()

        repo = NotificationRepository(session)
        result = await repo.get_delivery_log(notification.id, ChannelType.TELEGRAM)

        assert result is not None
        assert result.id == tg_log.id
        assert result.channel == ChannelType.TELEGRAM

    async def test_not_found_wrong_channel(self, session):
        """Если notification есть, но нужного канала нет, метод должен вернуть None."""
        user = make_user()
        session.add(user)
        await session.flush()

        notification = make_notification(user)
        session.add(notification)
        await session.flush()

        log = make_delivery_log(notification, ChannelType.EMAIL)
        session.add(log)
        await session.flush()

        repo = NotificationRepository(session)
        result = await repo.get_delivery_log(notification.id, ChannelType.TELEGRAM)

        assert result is None

    async def test_not_found_wrong_notification(self, session):
        """Даже с правильным каналом чужой notification_id не должен совпасть."""
        user = make_user()
        session.add(user)
        await session.flush()

        notification = make_notification(user)
        session.add(notification)
        await session.flush()

        log = make_delivery_log(notification, ChannelType.EMAIL)
        session.add(log)
        await session.flush()

        repo = NotificationRepository(session)
        result = await repo.get_delivery_log(uuid.uuid4(), ChannelType.EMAIL)

        assert result is None
