from src.models.user import User
from src.models.user_channel import ChannelType
from src.providers.email_provider import EmailProvider
from src.workers.base_worker import BaseWorker


class EmailWorker(BaseWorker):
    channel_type = ChannelType.EMAIL

    def __init__(self) -> None:
        super().__init__(EmailProvider())

    def get_recipient(self, user: User) -> str:
        return user.email
