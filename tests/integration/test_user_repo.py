import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from src.models.user import User
from src.models.user_channel import ChannelType, UserChannel
from src.repositories.user_repo import UserRepository

# Все integration-тесты гоняю на session-scoped loop,
# иначе asyncpg-соединение может оказаться привязанным к другому event loop.
pytestmark = pytest.mark.asyncio(loop_scope="session")


def make_user(**kwargs) -> User:
    """Создаю User с явным id и уникальными полями для предсказуемого SQL-сценария."""
    uid = uuid.uuid4()
    defaults = {
        "id": uid,
        "username": f"user_{uid.hex[:8]}",
        "email": f"{uid.hex[:8]}@test.com",
        "password_hash": "test-password-hash",
        "is_active": True,
    }
    return User(**{**defaults, **kwargs})


class TestGet:
    """Проверяю базовый get() по primary key."""

    async def test_success(self, session):
        """Если запись есть в БД, repo.get должен реально достать ее из PostgreSQL."""
        user = make_user()
        session.add(user)
        await session.flush()

        repo = UserRepository(session)
        result = await repo.get(user.id)

        assert result is not None
        assert result.id == user.id
        assert result.email == user.email

    async def test_not_found(self, session):
        """Неизвестный id должен вернуть None, потому что это часть контракта repo."""
        repo = UserRepository(session)
        result = await repo.get(uuid.uuid4())

        assert result is None


class TestCreate:
    """Проверяю вставку пользователя через BaseRepository.create()."""

    async def test_success(self, session):
        """После create() объект должен жить в сессии и содержать ожидаемые поля."""
        user = make_user()
        repo = UserRepository(session)

        result = await repo.create(user)

        assert result.id == user.id
        assert result.username == user.username
        assert result.email == user.email

    async def test_duplicate_email_raises(self, session):
        """UNIQUE по email проверяю на реальной БД, а не на доверии к модели."""
        email = f"dup_{uuid.uuid4().hex[:8]}@test.com"
        user1 = make_user(email=email)
        user2 = make_user(email=email)

        repo = UserRepository(session)
        await repo.create(user1)

        with pytest.raises(IntegrityError):
            await repo.create(user2)

    async def test_duplicate_username_raises(self, session):
        """Отдельно страхую UNIQUE по username как самостоятельное бизнес-правило."""
        username = f"dup_{uuid.uuid4().hex[:8]}"
        user1 = make_user(username=username)
        user2 = make_user(username=username)

        repo = UserRepository(session)
        await repo.create(user1)

        with pytest.raises(IntegrityError):
            await repo.create(user2)


class TestUpdate:
    """Проверяю обновление сохраненного пользователя."""

    async def test_success(self, session):
        """Меняю одно поле и убеждаюсь, что остальные значения не затираются."""
        user = make_user()
        repo = UserRepository(session)
        await repo.create(user)

        result = await repo.update(user, {"username": "updated_name"})

        assert result.username == "updated_name"
        assert result.email == user.email

    async def test_multiple_fields(self, session):
        """Проверяю реалистичный case, когда update меняет сразу несколько полей."""
        user = make_user()
        repo = UserRepository(session)
        await repo.create(user)

        new_email = f"new_{uuid.uuid4().hex[:8]}@test.com"
        result = await repo.update(user, {"username": "newname", "email": new_email})

        assert result.username == "newname"
        assert result.email == new_email


class TestGetByEmail:
    """Проверяю поиск пользователя по email."""

    async def test_success(self, session):
        """Точный email должен находить ровно того пользователя, которого я сохранил."""
        user = make_user()
        session.add(user)
        await session.flush()

        repo = UserRepository(session)
        result = await repo.get_by_email(user.email)

        assert result is not None
        assert result.id == user.id

    async def test_not_found(self, session):
        """Отсутствующий email должен вернуть пустой результат, а не ошибку."""
        repo = UserRepository(session)
        result = await repo.get_by_email("nobody@test.com")

        assert result is None

    async def test_case_sensitive(self, session):
        """Фиксирую текущее поведение: поиск идет по точному значению строки."""
        user = make_user(email="CaseSensitive@test.com")
        session.add(user)
        await session.flush()

        repo = UserRepository(session)

        assert await repo.get_by_email("CaseSensitive@test.com") is not None
        assert await repo.get_by_email("casesensitive@test.com") is None


class TestGetByUsername:
    """Проверяю поиск пользователя по username."""

    async def test_success(self, session):
        """Happy path для get_by_username()."""
        user = make_user()
        session.add(user)
        await session.flush()

        repo = UserRepository(session)
        result = await repo.get_by_username(user.username)

        assert result is not None
        assert result.id == user.id

    async def test_not_found(self, session):
        """Неизвестный username должен вернуть None как ожидаемый пустой контракт."""
        repo = UserRepository(session)
        result = await repo.get_by_username("nobody")

        assert result is None


class TestGetUserChannels:
    """Проверяю выборку включенных каналов пользователя."""

    async def test_returns_enabled_channels(self, session):
        """Метод должен вернуть только те каналы, которые включены у пользователя."""
        user = make_user()
        session.add(user)
        await session.flush()

        session.add_all(
            [
                UserChannel(
                    user_id=user.id,
                    channel=ChannelType.EMAIL,
                    is_enabled=True,
                ),
                UserChannel(
                    user_id=user.id,
                    channel=ChannelType.TELEGRAM,
                    is_enabled=True,
                ),
            ]
        )
        await session.flush()

        repo = UserRepository(session)
        result = await repo.get_user_channels(user.id)

        assert len(result) == 2
        channels = {channel.channel for channel in result}
        assert ChannelType.EMAIL in channels
        assert ChannelType.TELEGRAM in channels

    async def test_excludes_disabled_channels(self, session):
        """Выключенные каналы не должны просачиваться в выдачу."""
        user = make_user()
        session.add(user)
        await session.flush()

        session.add_all(
            [
                UserChannel(
                    user_id=user.id,
                    channel=ChannelType.EMAIL,
                    is_enabled=True,
                ),
                UserChannel(
                    user_id=user.id,
                    channel=ChannelType.TELEGRAM,
                    is_enabled=False,
                ),
            ]
        )
        await session.flush()

        repo = UserRepository(session)
        result = await repo.get_user_channels(user.id)

        assert len(result) == 1
        assert result[0].channel == ChannelType.EMAIL

    async def test_returns_empty_when_no_channels(self, session):
        """Если строк в user_channels нет, метод должен вернуть пустой список."""
        user = make_user()
        session.add(user)
        await session.flush()

        repo = UserRepository(session)
        result = await repo.get_user_channels(user.id)

        assert result == []

    async def test_returns_empty_when_all_disabled(self, session):
        """Если каналы есть, но все выключены, выдача тоже должна быть пустой."""
        user = make_user()
        session.add(user)
        await session.flush()

        session.add_all(
            [
                UserChannel(
                    user_id=user.id,
                    channel=ChannelType.EMAIL,
                    is_enabled=False,
                ),
                UserChannel(
                    user_id=user.id,
                    channel=ChannelType.TELEGRAM,
                    is_enabled=False,
                ),
            ]
        )
        await session.flush()

        repo = UserRepository(session)
        result = await repo.get_user_channels(user.id)

        assert result == []

    async def test_isolation_between_users(self, session):
        """Каналы одного пользователя не должны попадать в выборку другого."""
        user1 = make_user()
        user2 = make_user()
        session.add_all([user1, user2])
        await session.flush()

        session.add(
            UserChannel(
                user_id=user1.id,
                channel=ChannelType.EMAIL,
                is_enabled=True,
            )
        )
        await session.flush()

        repo = UserRepository(session)
        result = await repo.get_user_channels(user2.id)

        assert result == []
