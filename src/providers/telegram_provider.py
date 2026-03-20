from httpx import AsyncClient
from src.providers.base import BaseNotificationProvider, NotificationPayload
from src.config import settings

class TelegramProvider(BaseNotificationProvider):
    """Провайдер для отправки уведомлений через Telegram Bot API."""
    def __init__(self) -> None:
        self.httpx_client = AsyncClient()

    async def send(self, payload: NotificationPayload) -> None:
        """Отправляем уведомление через Telegram Bot API."""
        url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
        response = await self.httpx_client.post(
            url,
            json={
                "chat_id": payload.recipient,
                "text": f"{payload.title}\n\n{payload.body}",
            },
        )
        response.raise_for_status()  # бросит исключение если 4xx/5xx
        data = response.json()
        if not data.get("ok"):
            raise RuntimeError(f"Telegram API error: {data.get('description')}")


    async def close(self) -> None:
        await self.httpx_client.aclose()
