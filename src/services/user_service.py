from uuid import UUID

from src.exceptions import (
    EmailAlreadyExistsError,
    UsernameAlreadyExistsError,
    UserNotFoundError,
)
from src.models.user import User
from src.repositories.user_repo import UserRepository
from src.schemas.user import UserCreate, UserUpdate


class UserService:
    def __init__(self, repo: UserRepository) -> None:
        self.repo = repo

    async def create_user(self, user_create: UserCreate) -> User:
        existing = await self.repo.get_by_email(user_create.email)
        if existing:
            raise EmailAlreadyExistsError()
        existing = await self.repo.get_by_username(user_create.username)
        if existing:
            raise UsernameAlreadyExistsError()
        
        user = User(**user_create.model_dump())
        return await self.repo.create(user)

    async def get_user(self, user_id: UUID) -> User:
        user = await self.repo.get(user_id)
        if not user:
            raise UserNotFoundError()
        return user

    async def update_user(self, user_id: UUID, user_update: UserUpdate) -> User:
        user = await self.get_user(user_id)
        
        if user_update.username and user_update.username != user.username:
            existing = await self.repo.get_by_username(user_update.username)
            if existing:
                raise UsernameAlreadyExistsError()

        if user_update.email and user_update.email != user.email: 
            existing = await self.repo.get_by_email(user_update.email)
            if existing:
                raise EmailAlreadyExistsError()
        
        return await self.repo.update(user, user_update.model_dump(exclude_unset=True))