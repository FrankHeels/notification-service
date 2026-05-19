from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.user import User
from src.models.user_channel import UserChannel
from src.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    def __init__(self, session: AsyncSession):
        super().__init__(User, session)

    async def get_users(self) -> list[User]:
        results = await self.session.execute(select(User))
        return list(results.scalars().all())

    async def get_by_email(self, email: str) -> User | None:
        result = await self.session.execute(select(User).where(User.email == email))
        # scalar_one_or_none() возвращает единственный результат
        # или None, если нет совпадений. Если несколько совпадений, выбрасывает исключение.
        return result.scalar_one_or_none()

    async def get_by_username(self, username: str) -> User | None:
        result = await self.session.execute(
            select(User).where(User.username == username)
        )
        return result.scalar_one_or_none()

    async def get_user_channels(self, user_id: UUID) -> list[UserChannel]:
        result = await self.session.execute(
            select(UserChannel).where(
                UserChannel.user_id == user_id, UserChannel.is_enabled.is_(True)
            )
        )
        return list(result.scalars().all())
