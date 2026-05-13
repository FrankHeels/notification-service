from fastapi import APIRouter

from src.api.v1 import users, health, notifications, ws

router = APIRouter(prefix="/api/v1")
router.include_router(users.router)
router.include_router(health.router)
router.include_router(notifications.router)
router.include_router(ws.router)