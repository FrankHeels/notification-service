from src.models.user import User
from src.models.user_channel import ChannelType
from src.providers.sms_provider import SMSProvider
from src.workers.base_worker import BaseWorker


class SmsWorker(BaseWorker):
    channel_type = ChannelType.SMS

    def __init__(self) -> None:
        super().__init__(SMSProvider())

    def get_recipient(self, user: User) -> str:
        if not user.phone:
            raise ValueError(f"User {user.id} has no phone number")
        return user.phone
