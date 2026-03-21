import asyncio
import argparse

from src.rabbitmq import get_queue, init_rabbitmq, close_rabbitmq

from src.workers.email_worker import EmailWorker
from src.workers.sms_worker import SmsWorker
from src.workers.telegram_worker import TelegramWorker

WORKERS = {
    "email": EmailWorker,
    "telegram": TelegramWorker,
    "sms": SmsWorker,
}

async def main(channel: str) -> None:
    await init_rabbitmq()
    queue = await get_queue(channel)
    worker = WORKERS[channel]()
    await queue.consume(worker.process)
    try:
        await asyncio.Future()  # Run forever
    finally:
        await close_rabbitmq()



if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--channel", choices=["email", "telegram", "sms"], required=True, help="Channel to run the worker for")
    args = parser.parse_args()

    asyncio.run(main(args.channel))