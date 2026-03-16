from uuid import UUID
from typing import TypeVar, Generic, Any
from sqlalchemy.ext.asyncio import AsyncSession
from src.database import Base

T = TypeVar("T", bound=Base)

class BaseRepository(Generic[T]):
    def __init__(self, model: type[T], session: AsyncSession):
        self.model = model
        self.session = session

    async def get(self, id: UUID) -> T | None:
        return await self.session.get(self.model, id)
    
    async def create(self, obj: T) -> T:
        self.session.add(obj)
        await self.session.flush()  # Получаем ID после добавления
        return obj
    
    async def update(self, obj: T, data: dict[str, Any]) -> T:
        for key, value in data.items():
            setattr(obj, key, value)
        await self.session.flush() # Не commit(), чтобы изменения были зафиксированы в бд в get_db
        return obj