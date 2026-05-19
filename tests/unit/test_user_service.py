from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.exceptions import (
    EmailAlreadyExistsError,
    UsernameAlreadyExistsError,
    UserNotFoundError,
)
from src.schemas.user import UserCreate, UserUpdate
from src.services.user_service import UserService
from tests.factories import UserFactory


class TestCreateUser:
    """Проверяю ветки create_user и учусь тестировать orchestration сервиса."""

    async def test_success(self):
        """Happy path: сервис должен дойти до repo.create()."""
        # Беру готовый объект из фабрики, чтобы тест читался как сценарий,
        # а не как конструктор данных.
        user = UserFactory()

        # В unit-тесте мне важна логика сервиса,
        # поэтому репозиторий полностью подменяю моками.
        repo = MagicMock()
        repo.session.commit = AsyncMock(return_value=None)
        repo.get_by_email = AsyncMock(return_value=None)
        repo.get_by_username = AsyncMock(return_value=None)
        repo.create = AsyncMock(return_value=user)

        service = UserService(repo)
        data = UserCreate(username=user.username, email=user.email)

        result = await service.create_user(data)

        assert result == user
        repo.get_by_email.assert_awaited_once_with(user.email)
        repo.get_by_username.assert_awaited_once_with(user.username)
        repo.create.assert_awaited_once()

    async def test_email_already_exists(self):
        """Если email занят, сервис должен вернуть 409 и не идти дальше по сценарию."""
        existing_user = UserFactory()

        repo = MagicMock()
        repo.get_by_email = AsyncMock(return_value=existing_user)
        repo.get_by_username = AsyncMock()
        repo.create = AsyncMock()

        service = UserService(repo)
        data = UserCreate(username="newuser", email=existing_user.email)

        with pytest.raises(EmailAlreadyExistsError) as exc_info:
            await service.create_user(data)

        assert str(exc_info.value) == "User with this email already exists"
        repo.get_by_email.assert_awaited_once_with(existing_user.email)
        repo.get_by_username.assert_not_awaited()
        repo.create.assert_not_awaited()

    async def test_username_already_exists(self):
        """Отдельно страхую конфликт по username как другую ветку валидации."""
        existing_user = UserFactory()

        repo = MagicMock()
        repo.get_by_email = AsyncMock(return_value=None)
        repo.get_by_username = AsyncMock(return_value=existing_user)
        repo.create = AsyncMock()

        service = UserService(repo)
        data = UserCreate(username=existing_user.username, email="new@test.com")

        with pytest.raises(UsernameAlreadyExistsError) as exc_info:
            await service.create_user(data)

        assert str(exc_info.value) == "User with this username already exists"
        repo.get_by_email.assert_awaited_once_with("new@test.com")
        repo.get_by_username.assert_awaited_once_with(existing_user.username)
        repo.create.assert_not_awaited()


class TestGetUser:
    """Проверяю, как сервис превращает ответ repo в поведение приложения."""

    async def test_success(self):
        """Если repo нашло пользователя, сервис должен просто вернуть его."""
        user = UserFactory()

        repo = MagicMock()
        repo.get = AsyncMock(return_value=user)

        service = UserService(repo)
        result = await service.get_user(user.id)

        assert result == user
        repo.get.assert_awaited_once_with(user.id)

    async def test_not_found(self):
        """None из repo сервис обязан превратить в понятный для API 404."""
        repo = MagicMock()
        repo.get = AsyncMock(return_value=None)

        service = UserService(repo)

        with pytest.raises(UserNotFoundError) as exc_info:
            await service.get_user(uuid4())

        assert str(exc_info.value) == "User not found"


class TestUpdateUser:
    """Проверяю многошаговый сценарий update_user."""

    async def test_success(self):
        """Happy path: пользователь найден, а update доходит до repo."""
        user = UserFactory()
        updated_data = UserUpdate(username="updateduser", email="updated@test.com")

        repo = MagicMock()
        repo.get = AsyncMock(return_value=user)
        repo.get_by_email = AsyncMock(return_value=None)
        repo.get_by_username = AsyncMock(return_value=None)
        # Для простоты считаю, что repo.update вернет тот же объект после изменения.
        repo.update = AsyncMock(return_value=user)

        service = UserService(repo)
        result = await service.update_user(user.id, updated_data)

        assert result == user
        repo.get.assert_awaited_once_with(user.id)
        repo.get_by_username.assert_awaited_once_with("updateduser")
        repo.get_by_email.assert_awaited_once_with("updated@test.com")
        repo.update.assert_awaited_once()

    async def test_email_already_taken(self):
        """Если новый email уже занят, сервис должен остановиться до repo.update()."""
        user = UserFactory()
        existing_user = UserFactory()
        updated_data = UserUpdate(email=existing_user.email)

        repo = MagicMock()
        repo.get = AsyncMock(return_value=user)
        repo.get_by_email = AsyncMock(return_value=existing_user)
        repo.get_by_username = AsyncMock()
        repo.update = AsyncMock()

        service = UserService(repo)

        with pytest.raises(EmailAlreadyExistsError) as exc_info:
            await service.update_user(user.id, updated_data)

        assert str(exc_info.value) == "User with this email already exists"
        repo.get.assert_awaited_once_with(user.id)
        repo.get_by_email.assert_awaited_once_with(existing_user.email)
        repo.get_by_username.assert_not_awaited()
        repo.update.assert_not_awaited()
