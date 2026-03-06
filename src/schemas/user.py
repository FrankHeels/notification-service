import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

class UserCreate(BaseModel):
    username: str = Field(..., examples=["john_doe"])
    email: EmailStr = Field(..., examples=["john.doe@example.com"])
    telegram_id: int | None = Field(None, examples=[123456789])
    phone: str | None = Field(None, examples=["+1234567890"])

class UserUpdate(BaseModel):
    username: str | None = Field(None, examples=["john_doe"])
    email: EmailStr | None = Field(None, examples=["john.doe@example.com"])
    telegram_id: int | None = Field(None, examples=[123456789])
    phone: str | None = Field(None, examples=["+1234567890"])

class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    email: EmailStr
    telegram_id: int | None
    phone: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

class UserChannelUpdate(BaseModel):
    channel: str = Field(..., examples=["email", "telegram", "sms"])
    is_enabled: bool = Field(..., examples=[True, False])

class UserChannelResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    channel: str
    is_enabled: bool