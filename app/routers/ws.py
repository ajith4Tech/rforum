import asyncio
import json
import uuid
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from redis.asyncio import Redis

router = APIRouter(tags=["websocket"])

# Unique identifier for this process to avoid re-broadcasting our own Redis messages
SERVER_ID = str(uuid.uuid4())

# Events that clients are permitted to relay through the WebSocket.
# Unknown or unlisted event types are silently dropped to prevent UI injection.
ALLOWED_WS_EVENTS = frozenset({
    "slide_change", "page_change", "session_update",
    "response_submitted", "new_response", "upvote", "heartbeat",
})

# Maximum raw message size accepted from a client (64 KB)
MAX_WS_MESSAGE_BYTES = 65_536


class ConnectionManager:
    """
    Manages WebSocket connections grouped by session code.

    One shared Redis pubsub task per session code (not per connection).
    With 80 audience members in one session this means 1 Redis subscription
    instead of 80, and JSON is serialised once and fanned out to all sockets.
    """

    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = {}
        self._pubsub_tasks: dict[str, asyncio.Task] = {}

    async def connect(self, session_code: str, websocket: WebSocket, redis: Redis) -> None:
        await websocket.accept()
        if session_code not in self._connections:
            self._connections[session_code] = set()
            # Shared pubsub listener — started once per session, not per socket
            pubsub = redis.pubsub()
            await pubsub.subscribe(f"session:{session_code}")
            task = asyncio.create_task(
                self._listen(session_code, pubsub),
                name=f"pubsub:{session_code}",
            )
            self._pubsub_tasks[session_code] = task
        self._connections[session_code].add(websocket)

    async def disconnect(self, session_code: str, websocket: WebSocket) -> None:
        bucket = self._connections.get(session_code)
        if not bucket:
            return
        bucket.discard(websocket)
        if not bucket:
            del self._connections[session_code]
            task = self._pubsub_tasks.pop(session_code, None)
            if task:
                task.cancel()

    async def broadcast(self, session_code: str, message: dict) -> None:
        bucket = self._connections.get(session_code)
        if not bucket:
            return
        # Serialise once, send to every socket
        payload = json.dumps(message)
        dead: list[WebSocket] = []
        for ws in list(bucket):
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.disconnect(session_code, ws)

    async def _listen(self, session_code: str, pubsub) -> None:
        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    try:
                        data = json.loads(message["data"])
                        if data.get("origin") == SERVER_ID:
                            continue
                        await self.broadcast(session_code, data)
                    except (json.JSONDecodeError, KeyError):
                        pass
        except asyncio.CancelledError:
            await pubsub.unsubscribe(f"session:{session_code}")


manager = ConnectionManager()


@router.websocket("/ws/{session_code}")
async def websocket_endpoint(websocket: WebSocket, session_code: str):
    redis: Redis = websocket.app.state.redis
    await manager.connect(session_code, websocket, redis)
    try:
        while True:
            try:
                data = await websocket.receive_text()
                # Drop oversized messages
                if len(data) > MAX_WS_MESSAGE_BYTES:
                    continue
                message = json.loads(data)
                if not isinstance(message, dict):
                    continue
                # Drop unknown event types to prevent UI injection by guests
                if message.get("event") not in ALLOWED_WS_EVENTS:
                    continue
                message.setdefault("origin", SERVER_ID)
                await manager.broadcast(session_code, message)
                await redis.publish(f"session:{session_code}", json.dumps(message))
            except WebSocketDisconnect:
                break
            except Exception as e:
                print(f"[WS] Error: {e}")
                break
    finally:
        await manager.disconnect(session_code, websocket)
