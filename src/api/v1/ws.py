import asyncio
import json
from typing import Any

import redis.asyncio as redis
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from structlog import get_logger

from src.redis import consume_guest_ws_ticket, create_guest_ws_ticket, redis_pool
from src.services.public_stream import PUBLIC_EVENTS_STREAM

router = APIRouter(prefix="/ws", tags=["WebSocket"])
logger = get_logger()

REPLAY_LIMIT = 100
XREAD_BLOCK_MS = 5000
SEND_TIMEOUT_SECONDS = 5


class TicketResponse(BaseModel):
    ticket: str


@router.post("/guest-ticket", response_model=TicketResponse)
async def generate_guest_ticket() -> TicketResponse:
    ticket = await create_guest_ws_ticket()
    return TicketResponse(ticket=ticket)


@router.websocket("/dashboard")
async def dashboard_ws(
    websocket: WebSocket,
    ticket: str = Query(...),
    last_event_id: str | None = Query(None),
) -> None:
    is_guest = await consume_guest_ws_ticket(ticket)
    if not is_guest:
        await websocket.close(code=1008, reason="Invalid or expired ticket")
        return

    await websocket.accept()
    redis_client = redis.Redis(connection_pool=redis_pool)

    try:
        current_id = await _send_replay(websocket, redis_client, last_event_id)
        await _send_live_events(websocket, redis_client, current_id)
    except WebSocketDisconnect:
        logger.info("Dashboard WebSocket disconnected")
    except asyncio.CancelledError:
        raise
    finally:
        await redis_client.aclose()


async def _send_replay(
    websocket: WebSocket,
    redis_client: redis.Redis,
    last_event_id: str | None,
) -> str:
    if last_event_id:
        entries = await redis_client.xrange(
            PUBLIC_EVENTS_STREAM,
            min=f"({last_event_id}",
            max="+",
            count=REPLAY_LIMIT,
        )
        current_id = last_event_id
    else:
        entries = await redis_client.xrevrange(
            PUBLIC_EVENTS_STREAM,
            max="+",
            min="-",
            count=REPLAY_LIMIT,
        )
        entries = list(reversed(entries))
        current_id = "0-0"

    for entry_id, fields in entries:
        event = _stream_entry_to_public_event(entry_id, fields)
        await _send_event(websocket, event)
        current_id = event["event_id"]

    return current_id


async def _send_live_events(
    websocket: WebSocket,
    redis_client: redis.Redis,
    last_event_id: str,
) -> None:
    current_id = last_event_id

    while True:
        result = await redis_client.xread(
            streams={PUBLIC_EVENTS_STREAM: current_id},
            count=10,
            block=XREAD_BLOCK_MS,
        )
        if not result:
            continue

        for _, entries in result:
            for entry_id, fields in entries:
                event = _stream_entry_to_public_event(entry_id, fields)
                await _send_event(websocket, event)
                current_id = event["event_id"]


async def _send_event(websocket: WebSocket, event: dict[str, Any]) -> None:
    await asyncio.wait_for(
        websocket.send_json(event),
        timeout=SEND_TIMEOUT_SECONDS,
    )


def _stream_entry_to_public_event(
    entry_id: str | bytes,
    fields: dict[str | bytes, Any],
) -> dict[str, Any]:
    payload = _field(fields, "payload")
    event = json.loads(payload)
    event["event_id"] = _decode(entry_id)
    return event


def _field(fields: dict[str | bytes, Any], name: str) -> str:
    value = fields.get(name)
    if value is None:
        value = fields.get(name.encode())
    if value is None:
        raise ValueError(f"Redis stream entry has no {name!r} field")
    return _decode(value)


def _decode(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)
