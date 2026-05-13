import asyncio
from uuid import UUID

from fastapi import WebSocket, WebSocketDisconnect, APIRouter, Depends, Query
from pydantic import BaseModel
from structlog import get_logger

from src.redis import create_ws_ticket, consume_ws_ticket, redis_pool
from src.api.dependencies import get_current_user
import redis.asyncio as redis


router = APIRouter(prefix="/ws", tags=["WebSocket"])
logger = get_logger()

class TickerResponse(BaseModel):
    ticket: str


class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[UUID, set[WebSocket]] = {}
        self.redis_client = redis.Redis(connection_pool=redis_pool)
        self.pubsub = self.redis_client.pubsub()
        self.listener_task = None

    async def connect(self, websocket: WebSocket, user_id: UUID):
        await websocket.accept()
        logger.info("WebSocket accepted", user_id=str(user_id))
        if user_id not in self.active_connections:
            self.active_connections[user_id] = set()
            channel_name = f"notifications:user:{user_id}"
            await self.pubsub.subscribe(channel_name)
            logger.info("Subscribed to Redis channel", channel=channel_name)
            if self.listener_task is None:
                logger.info("Starting Redis listener task")
                self.listener_task = asyncio.create_task(self._listen_to_redis())
        self.active_connections[user_id].add(websocket)
        logger.info("WebSocket connected", user_id=str(user_id))

    
    async def disconnect(self, websocket: WebSocket, user_id: UUID):
        if user_id in self.active_connections:
            self.active_connections[user_id].discard(websocket)
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
                await self.pubsub.unsubscribe(f"notifications:user:{user_id}")
                logger.info("WebSocket disconnected", user_id=str(user_id))


    async def _listen_to_redis(self):
        logger.info("Redis listener loop started")
        try:
            async for message in self.pubsub.listen():
                if message["type"] == "message":
                    channel = message["channel"]
                    user_id_str = channel.split(":")[-1]
                    logger.info("Received message from Redis", channel=channel, user_id=user_id_str)
                    try:
                        user_id = UUID(user_id_str)
                        if user_id in self.active_connections:
                            data = message["data"]
                            logger.info("Forwarding to WebSockets", user_id=user_id_str, count=len(self.active_connections[user_id]))
                            disconnected = set()
                            for ws in self.active_connections[user_id]:
                                try:
                                    await ws.send_text(data)
                                except Exception as e:
                                    logger.error("Send failed", error=str(e))
                                    disconnected.add(ws)
                            
                            for ws in disconnected:
                                await self.disconnect(ws, user_id)
                        else:
                            logger.warning("No active connections for user", user_id=user_id_str)
                    except ValueError:
                        pass
        except Exception as e:
            logger.info("Redis listener stopped", error=str(e))


manager = ConnectionManager()

@router.post("/ticket", response_model=TickerResponse)
async def generate_ticket(
    current_user = Depends(get_current_user)
):
    ticket = await create_ws_ticket(current_user.id)
    return TickerResponse(ticket=ticket)


@router.websocket("/dashboard")
async def dashboard_ws(
    websocket: WebSocket,
    ticket: str = Query(...)
):
    user_id = await consume_ws_ticket(ticket)

    if not user_id:
        await websocket.close(code=1008, reason="Invalid or expired ticket")  # Policy Violation
        return
    
    await manager.connect(websocket, user_id)

    try:
        while True:
            await websocket.receive_text()  # Просто поддерживаем соединение открытым
    except WebSocketDisconnect:
        await manager.disconnect(websocket, user_id)

        
                            

                
