import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from src.models.notification import Priority, Status
from src.schemas.delivery import DeliveryLogResponse


class NotificationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idempotency_key: str
    title: str = Field(..., examples=["New Message"])
    body: str = Field(..., examples=["You have a new message from John."])
    priority: Priority = Field(Priority.NORMAL, examples=["low", "normal", "high"])


class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    idempotency_key: str
    title: str
    body: str
    priority: Priority
    status: Status
    created_at: datetime
    deliveries: list[DeliveryLogResponse] = []
