from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from src.config import settings


engine = create_async_engine(
    str(settings.database_url),
    echo=False,       # True — выводить SQL-запросы в консоль (удобно при отладке)
    pool_size=10,     # постоянных соединений в пуле
    max_overflow=20,  # доп. соединений сверх pool_size при пиковой нагрузке
    pool_pre_ping=True,  # проверять соединение перед использованием
)

AsyncSessionFactory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,  # не сбрасывать атрибуты объектов после commit
)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: provides a transactional async DB session.

    Commits on success, rolls back on any exception.
    One HTTP request = one transaction.

    Yields:
        AsyncSession: active SQLAlchemy async session.
    """
    async with AsyncSessionFactory() as session: # Создает новую сессию (соединеие с БД)
        try:
            yield session # Передача сессии в роутер FastAPI
            await session.commit()
        except Exception:
            await session.rollback()
            raise
