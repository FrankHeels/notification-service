import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from src.models.delivery_log import DeliveryStatus
from src.models.user_channel import ChannelType

class DeliveryLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: uuid.UUID
    notification_id: uuid.UUID
    channel: ChannelType
    status: DeliveryStatus
    attempts: int
    last_error: str | None
    sent_at: datetime | None
    created_at: datetime