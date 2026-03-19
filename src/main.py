from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.api.router import router
from src.rabbitmq import init_rabbitmq, close_rabbitmq

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

app.include_router(router)
