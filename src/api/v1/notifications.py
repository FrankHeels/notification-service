from uuid import UUID

from fastapi import APIRouter, Depends, status

from src.api.dependencies import get_current_user, get_notification_service
from src.exceptions import NotificationAccessDeniedError
from src.models.user import User
from src.schemas.notification import NotificationCreate, NotificationResponse
from src.services.notification_service import NotificationService

router = APIRouter(prefix="/notifications", tags=["Notifications"])

@router.get("/", response_model=list[NotificationResponse])
async def get_notifications(
    skip: int = 0,
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    notification_service: NotificationService = Depends(get_notification_service),
) -> list[NotificationResponse]:
    return await notification_service.get_user_notifications(
        current_user.id, skip, limit
    )

@router.get("/{notification_id}", response_model=NotificationResponse)
async def get_notification(
    notification_id: UUID,
    notification_service: NotificationService = Depends(get_notification_service),
    current_user: User = Depends(get_current_user),
) -> NotificationResponse:
    notification = await notification_service.get_notification(notification_id)
    if notification.user_id != current_user.id:
        raise NotificationAccessDeniedError()
    return notification

@router.post(
    "/send",
    response_model=NotificationResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def send_notification(
    data: NotificationCreate,
    notification_service: NotificationService = Depends(get_notification_service),
    current_user: User = Depends(get_current_user),
) -> NotificationResponse:
    data.user_id = current_user.id
    return await notification_service.send_notification(data)

