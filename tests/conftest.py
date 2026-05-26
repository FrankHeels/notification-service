import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from testcontainers.postgres import PostgresContainer

from src.database import Base, get_db
from src.main import app


@pytest.fixture(scope="session")
async def engine():
    """Поднимаем одну тестовую PostgreSQL на весь прогон.
    Это быстрее, чем создавать контейнер заново под каждый тест.
    """
    with PostgresContainer("postgres:16") as pg:
        # testcontainers отдает sync URL с psycopg2, а приложению нужен asyncpg.
        url = pg.get_connection_url().replace("psycopg2", "asyncpg")
        engine = create_async_engine(url)

        # Таблицы создаются один раз, чтобы дальше тесты работали с живой схемой.
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        yield engine
        await engine.dispose()


@pytest.fixture
async def session(engine):
    """Даю отдельную async session на каждый тест.
    После теста откатываю изменения, чтобы следующий стартовал с чистого состояния.
    """
    async with AsyncSession(engine) as session:
        yield session
        await session.rollback()


@pytest.fixture
async def client(session):
    """Подменяю get_db, чтобы FastAPI использовал тестовую сессию.
    Так HTTP-тесты ходят в реальную тестовую БД, но при этом остаются изолированными.
    """

    async def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db

    # AsyncClient ходит прямо в приложение без реального сетевого сервера.
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()
