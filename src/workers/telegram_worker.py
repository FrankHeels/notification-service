from src.models.user import User
from src.models.user_channel import ChannelType
from src.providers.telegram_provider import TelegramProvider
from src.workers.base_worker import BaseWorker


class TelegramWorker(BaseWorker):
    channel_type = ChannelType.TELEGRAM

    def __init__(self) -> None:
        super().__init__(TelegramProvider())

    def get_recipient(self, user: User) -> str:
        if not user.telegram_id:
            raise ValueError(f"User {user.id} has no telegram_id")
        return str(user.telegram_id)
