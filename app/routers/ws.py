import asyncio
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from redis.asyncio import Redis

router = APIRouter(tags=["websocket"])


class ConnectionManager:
    """Manages WebSocket connections grouped by session code."""

    def __init__(self):
        self.connections: dict[str, list[WebSocket]] = {}

    async def connect(self, session_code: str, websocket: WebSocket):
        await websocket.accept()
        if session_code not in self.connections:
            self.connections[session_code] = []
        self.connections[session_code].append(websocket)

    def disconnect(self, session_code: str, websocket: WebSocket):
        if session_code in self.connections:
            self.connections[session_code].remove(websocket)
            if not self.connections[session_code]:
                del self.connections[session_code]

    async def broadcast(self, session_code: str, message: dict):
        if session_code in self.connections:
            dead = []
            for ws in self.connections[session_code]:
                try:
                    await ws.send_json(message)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                self.disconnect(session_code, ws)


manager = ConnectionManager()


@router.websocket("/ws/{session_code}")
async def websocket_endpoint(websocket: WebSocket, session_code: str):
    redis: Redis = websocket.app.state.redis
    await manager.connect(session_code, websocket)

    pubsub = redis.pubsub()
    await pubsub.subscribe(f"session:{session_code}")

    async def listen_redis():
        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    try:
                        data = json.loads(message["data"])
                        # All local clients connected to this instance 
                        # get the message via this broadcast call.
                        await manager.broadcast(session_code, data)
                    except (json.JSONDecodeError, KeyError):
                        pass
        except asyncio.CancelledError:
            pass

    redis_task = asyncio.create_task(listen_redis())

    try:
        while True:
            try:
                # Receive message from user
                data = await websocket.receive_text()
                message = json.loads(data)

                # FIX: ONLY publish to Redis. 
                # Do NOT call manager.broadcast(session_code, message) here.
                # The 'listen_redis' task above will receive the Redis event 
                # and broadcast it to everyone, including this sender.
                await redis.publish(
                    f"session:{session_code}", json.dumps(message)
                )
                
            except WebSocketDisconnect:
                break
            except Exception as e:
                print(f"[WS] Error: {e}")
                break
    finally:
        redis_task.cancel()
        await pubsub.unsubscribe(f"session:{session_code}")
        manager.disconnect(session_code, websocket)
