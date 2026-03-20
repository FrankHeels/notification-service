from structlog import get_logger
from src.providers.base import BaseNotificationProvider, NotificationPayload

class SMSProvider(BaseNotificationProvider):
    """Провайдер для отправки SMS-уведомлений через сторонний сервис."""
    def __init__(self) -> None:
        self.logger = get_logger()

    async def send(self, payload: NotificationPayload) -> None:
        """Отправляем уведомление через SMS."""
        self.logger.info(
            "SMS sent (stub)",
            recipient=payload.recipient,
            title=payload.title,
            body=payload.body
        )