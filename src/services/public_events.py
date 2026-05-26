from datetime import UTC, datetime
from uuid import UUID

from src.models.delivery_log import DeliveryStatus
from src.models.notification import Priority
from src.models.user_channel import ChannelType


def build_notification_created_event(
    *,
    notification_id: UUID,
    username: str,
    priority: Priority,
    channels: list[ChannelType],
) -> dict:
    return {
        "type": "notification.created",
        "notification_id": str(notification_id),
        "username": username,
        "priority": priority.value,
        "channels": [channel.value for channel in channels],
        "occurred_at": datetime.now(UTC).isoformat(),
    }


def build_delivery_updated_event(
    *,
    notification_id: UUID,
    username: str,
    channel: ChannelType,
    status: DeliveryStatus | str,
    attempts: int,
    public_reason: str | None = None,
) -> dict:
    payload = {
        "type": "delivery.updated",
        "notification_id": str(notification_id),
        "username": username,
        "channel": channel.value,
        "status": status.value if isinstance(status, DeliveryStatus) else status,
        "attempts": attempts,
        "occurred_at": datetime.now(UTC).isoformat(),
    }

    if public_reason is not None:
        payload["public_reason"] = public_reason

    return payload

