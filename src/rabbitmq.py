from aio_pika import connect_robust, ExchangeType
from aio_pika.abc import AbstractConnection, AbstractChannel, AbstractExchange
from src.config import settings

_connection: AbstractConnection | None = None
_channel: AbstractChannel | None = None
_exchange: AbstractExchange | None = None

EXCHANGE_NAME = "notifications"
QUEUES = {
    "email": "notifications.email",
    "telegram": "notifications.telegram",
    "sms": "notifications.sms"
}

async def init_rabbitmq() -> None:
    global _connection, _channel, _exchange

    _connection = await connect_robust(str(settings.rabbitmq_url))
    _channel = await _connection.channel()
    await _channel.set_qos(prefetch_count=10)
    _exchange = await _channel.declare_exchange(EXCHANGE_NAME, ExchangeType.DIRECT)

    for routing_key ,queue_name in QUEUES.items():
        queue = await _channel.declare_queue(queue_name, durable=True)
        await queue.bind(_exchange, routing_key=routing_key)

async def get_queue(channel: str) -> str:
    if channel not in QUEUES:
        raise ValueError(f"Invalid channel type: {channel}")
    return QUEUES[channel]

async def get_exchange() -> AbstractExchange:
    if _exchange is None:
        raise RuntimeError("RabbitMQ exchange not initialized")
    return _exchange

async def close_rabbitmq() -> None:
    if _connection:
        await _connection.close()