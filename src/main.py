from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.api.router import router

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown events."""
    # --- startup ---
    # TODO: подключить Redis, RabbitMQ когда реализуем
    yield
    # --- shutdown ---
    # TODO: закрыть соединения когда реализуем


app = FastAPI(
    title="Notification Service",
    description="Async notification delivery via email, Telegram and SMS",
    version="0.1.0",
    lifespan=lifespan,
)


# TODO: подключить роутеры когда реализуем api/
app.include_router(router)
