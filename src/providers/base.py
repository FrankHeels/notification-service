from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class NotificationPayload:
    title: str
    body: str
    recipient: str  # email / telegram / sms


class BaseNotificationProvider(ABC):
    """Базовый интерфейс для провайдеров уведомлений.""" 

    @abstractmethod
    async def send(self, payload: NotificationPayload) -> None:
        ...