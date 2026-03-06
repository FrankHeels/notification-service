import uuid
from enum import Enum

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base

class ChannelType(str, Enum):
    EMAIL = "email"
    TELEGRAM = "telegram"
    SMS = "sms"

class UserChannel(Base):
    __tablename__ = "user_channels"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    channel: Mapped[ChannelType] = mapped_column(primary_key=True)
    is_enabled: Mapped[bool] = mapped_column(default=True)