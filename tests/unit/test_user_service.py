from uuid import uuid4
import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi import HTTPException

from src.services.user_service import UserService
from src.schemas.user import UserCreate, UserUpdate
from tests.factories import UserFactory


class TestCreateUser:
    async def test_success(self):
        # создаём объект User через фабрику — реалистичные данные без ручного заполнения
        user = UserFactory()

        # мокаем репозиторий — не нужна реальная БД
        repo = MagicMock()
        repo.get_by_email = AsyncMock(return_value=None)     # email свободен
        repo.get_by_username = AsyncMock(return_value=None)  # username свободен
        repo.create = AsyncMock(return_value=user)           # создание вернёт объект

        service = UserService(repo)
        data = UserCreate(username=user.username, email=user.email)

        result = await service.create_user(data)

        # проверяем что вернулся правильный объект
        assert result == user
        # проверяем что create был вызван ровно один раз
        repo.create.assert_called_once()

    async def test_email_already_exists(self):
        existing_user = UserFactory()

        repo = MagicMock()
        # имитируем что email уже занят — репозиторий вернул существующего пользователя
        repo.get_by_email = AsyncMock(return_value=existing_user)

        service = UserService(repo)
        data = UserCreate(username="newuser", email=existing_user.email)

        # pytest.raises проверяет что метод БРОСИЛ исключение
        with pytest.raises(HTTPException) as exc_info:
            await service.create_user(data)

        # проверяем что это именно 409, а не 404 или 500
        assert exc_info.value.status_code == 409
        # create не должен был вызываться — зачем создавать если email занят
        repo.create.assert_not_called()

    async def test_username_already_exists(self):
        existing_user = UserFactory()

        repo = MagicMock()
        # email свободен, но username занят
        repo.get_by_email = AsyncMock(return_value=None)
        repo.get_by_username = AsyncMock(return_value=existing_user)

        service = UserService(repo)
        data = UserCreate(username=existing_user.username, email="new@test.com")

        with pytest.raises(HTTPException) as exc_info:
            await service.create_user(data)

        assert exc_info.value.status_code == 409
        repo.create.assert_not_called()


class TestGetUser:
    async def test_success(self):
        user = UserFactory()

        repo = MagicMock()
        repo.get = AsyncMock(return_value=user) # пользователя найден

        service = UserService(repo)
        
        result = await service.get_user(user.id)

        assert result == user

        repo.get.assert_called_once_with(user.id)

    async def test_not_found(self):
        repo = MagicMock()
        repo.get = AsyncMock(return_value=None)

        service = UserService(repo)

        with pytest.raises(HTTPException) as exc_info:
            await service.get_user(uuid4())

        assert exc_info.value.status_code == 404

class TestUpdateUser:
    async def test_success(self):
        user = UserFactory()
        updated_data = UserUpdate(username="updateduser", email="updated@test.com")
        
        repo = MagicMock()
        repo.get = AsyncMock(return_value=user)  # пользователь найден
        repo.get_by_email = AsyncMock(return_value=None)     # email свободен
        repo.get_by_username = AsyncMock(return_value=None)  # username свободен
        repo.update = AsyncMock(return_value=user) # обновление вернёт тот же объект для простоты теста

        service = UserService(repo)
        
        result = await service.update_user(user.id, updated_data)

        assert result == user
        repo.update.assert_called_once()

    async def test_email_already_taken(self):
        user = UserFactory()
        existing_user = UserFactory()
        updated_data = UserUpdate(email=existing_user.email)

        repo = MagicMock()
        repo.get = AsyncMock(return_value=user)  # пользователь найден
        repo.get_by_email = AsyncMock(return_value=existing_user)  # email занят

        service = UserService(repo)
        with pytest.raises(HTTPException) as exc_info:
            await service.update_user(user.id, updated_data)

        assert exc_info.value.status_code == 409
