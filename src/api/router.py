from fastapi import APIRouter

from src.api.v1 import users, health

router = APIRouter(prefix="/api/v1")
router.include_router(users.router)
router.include_router(health.router)