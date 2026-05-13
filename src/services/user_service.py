from uuid import UUID

from src.exceptions import (
    EmailAlreadyExistsError,
    UsernameAlreadyExistsError,
    UserNotFoundError,
)
from src.models.user import User
from src.models.user_channel import UserChannel, ChannelType
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
        created_user = await self.repo.create(user)

        if user_create.email:
            email_channel = UserChannel(
                user_id=created_user.id, 
                channel=ChannelType.EMAIL, 
                is_enabled=True
            )
            self.repo.session.add(email_channel)

        if user_create.telegram_id:
            tg_channel = UserChannel(
                user_id=created_user.id, 
                channel=ChannelType.TELEGRAM, 
                is_enabled=True
            )
            self.repo.session.add(tg_channel)

        await self.repo.session.commit()
        return created_user


    async def get_user(self, user_id: UUID) -> User:
        user = await self.repo.get(user_id)
        if not user:
            raise UserNotFoundError()
        return user

    
    async def get_users(self) -> list[User]:
        result = await self.repo.get_users()
        return result


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