from aio_pika import ExchangeType, connect_robust
from aio_pika.abc import (
    AbstractChannel,
    AbstractConnection,
    AbstractExchange,
    AbstractQueue,
)
from src.config import settings

_connection: AbstractConnection | None = None
_channel: AbstractChannel | None = None
_exchange: AbstractExchange | None = None
_queues: dict[str, AbstractQueue] = {}

EXCHANGE_NAME = "notifications"
QUEUES = {
    "email": "notifications.email",
    "telegram": "notifications.telegram",
}

async def init_rabbitmq() -> None:
    global _connection, _channel, _exchange, _queues

    _connection = await connect_robust(str(settings.rabbitmq_url))
    _channel = await _connection.channel()
    await _channel.set_qos(prefetch_count=10)
    _exchange = await _channel.declare_exchange(EXCHANGE_NAME, ExchangeType.DIRECT)

    _queues = {}

    for routing_key, queue_name in QUEUES.items():
        queue = await _channel.declare_queue(queue_name, durable=True)
        await queue.bind(_exchange, routing_key=routing_key)
        _queues[routing_key] = queue

async def is_connected() -> bool:
    return _connection is not None and not _connection.is_closed

async def get_queue(channel: str) -> AbstractQueue:
    if channel not in QUEUES:
        raise ValueError(f"Invalid channel type: {channel}")
    if not _queues:
        raise RuntimeError("RabbitMQ queues not initialized")
    return _queues[channel]

async def get_exchange() -> AbstractExchange:
    if _exchange is None:
        raise RuntimeError("RabbitMQ exchange not initialized")
    return _exchange

async def close_rabbitmq() -> None:
    global _connection, _channel, _exchange, _queues

    if _channel and not _channel.is_closed:
        await _channel.close()
    if _connection and not _connection.is_closed:
        await _connection.close()

    _connection = None
    _channel = None
    _exchange = None
    _queues = {}
