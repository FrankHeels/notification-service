import aiosmtplib
from email.message import EmailMessage
from src.providers.base import BaseNotificationProvider, NotificationPayload
from src.config import settings

class EmailProvider(BaseNotificationProvider):
    """Провайдер для отправки email-уведомлений через SMTP."""
    async def send(self, payload: NotificationPayload) -> None:
        """Отправляем письмо через SMTP-сервер."""
        message = EmailMessage()
        message["From"] = "noreply@notification.service"
        message["To"] = payload.recipient
        message["Subject"] = payload.title
        message.set_content(payload.body)

        
        await aiosmtplib.send(
            message,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
        )