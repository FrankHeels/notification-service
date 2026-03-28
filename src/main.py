from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.api.exception_handler import register_exception_handlers
from src.api.router import router
from src.rabbitmq import close_rabbitmq, init_rabbitmq


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown events."""
    # --- startup ---
    await init_rabbitmq()
    yield
    # --- shutdown ---
    await close_rabbitmq()

app = FastAPI(
    title="Notification Service",
    description="Async notification delivery via email, Telegram and SMS",
    version="0.1.0",
    lifespan=lifespan,
)

register_exception_handlers(app)

app.include_router(router)
