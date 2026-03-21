import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from testcontainers.postgres import PostgreSqlContainer

from src.database import Base, get_db
from src.main import app


# scope="session" — контейнер запускается ОДИН раз на весь прогон тестов,
# а не на каждый тест. Это экономит время — Docker не пересоздаёт БД каждый раз.
@pytest.fixture(scope="session")
async def engine():
    # testcontainers поднимает реальный Docker-контейнер с PostgreSQL
    with PostgreSqlContainer("postgres:16") as pg:
        # заменяем драйвер: testcontainers даёт postgresql://, нужен asyncpg
        url = pg.get_connection_url().replace(
            "postgresql://", "postgresql+asyncpg://"
        )
        engine = create_async_engine(url)
        # создаём все таблицы из наших моделей в тестовой БД
        # run_sync нужен потому что create_all — синхронный метод
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        yield engine
        # закрываем пул соединений после всех тестов
        await engine.dispose()


# без scope — новая сессия (транзакция) на каждый тест
@pytest.fixture
async def session(engine):
    async with AsyncSession(engine) as session:
        yield session
        # откатываем все изменения после теста — следующий тест получает чистую БД
        await session.rollback()


@pytest.fixture
async def client(session):
    # подменяем get_db: вместо реальной БД FastAPI получает нашу тестовую сессию.
    # это позволяет откатить все изменения после теста через session.rollback()
    async def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    # AsyncClient делает HTTP-запросы напрямую в FastAPI без реального сетевого соединения
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client
    # очищаем переопределения чтобы не влиять на следующие тесты
    app.dependency_overrides.clear()
