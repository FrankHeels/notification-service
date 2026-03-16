from uuid import UUID
from fastapi import APIRouter, Depends, status

from src.services.user_service import UserService
from src.schemas.user import UserCreate, UserUpdate, UserResponse
from src.api.dependencies import get_user_service

router = APIRouter(prefix='/users', tags=['Users'])

@router.get('/{user_id}', response_model=UserResponse)
async def get_user(
    user_id: UUID,
    service: UserService = Depends(get_user_service)):
    
    return await service.get_user(user_id)

@router.post('/', response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    user_create: UserCreate,
    service: UserService = Depends(get_user_service)):
    
    return await service.create_user(user_create)

@router.patch('/{user_id}', response_model=UserResponse)
async def update_user(
    user_id: UUID,
    user_update: UserUpdate,
    service: UserService = Depends(get_user_service)):

    return await service.update_user(user_id, user_update)


