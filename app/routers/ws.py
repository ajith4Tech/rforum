import asyncio
import json
import logging
import uuid
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jose import JWTError, jwt
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import select

from app.config import get_settings
from app.database import async_session
from app.models import Session, User, UserRole
from app.rate_limit import check_rate_limit

logger = logging.getLogger(__name__)
router = APIRouter(tags=["websocket"])
settings = get_settings()

# Unique identifier for this process to avoid re-broadcasting our own Redis messages
SERVER_ID = str(uuid.uuid4())

# Events that clients are permitted to relay through the WebSocket.
# Unknown or unlisted event types are silently dropped to prevent UI injection.
#
# "response_submitted"/"new_response"/"upvote" are NOT here on purpose: those
# are authoritative broadcasts published to Redis only by the REST endpoints
# in app/routers/responses.py after persisting to the DB (see submit_response/
# upvote_response), then relayed to every socket by ConnectionManager._listen
# — which does not consult this set. If a client were allowed to send these
# event names directly, any guest could forge a fake response/upvote that
# appears live to the moderator and every other viewer without ever hitting
# the DB, rate limits, or validation.
ALLOWED_WS_EVENTS = frozenset({
    "slide_change", "page_change", "session_update", "heartbeat",
})

# Control events that only an authenticated session owner (or admin) may relay.
# Everyone else connecting to a session code is a guest or a read-only screen.
MODERATOR_ONLY_EVENTS = frozenset({"slide_change", "page_change", "session_update"})

# Maximum raw message size accepted from a client (64 KB)
MAX_WS_MESSAGE_BYTES = 65_536


async def _get_session_by_code(session_code: str) -> Session | None:
    async with async_session() as db:
        result = await db.execute(select(Session).where(Session.unique_code == session_code))
        return result.scalar_one_or_none()


async def resolve_ws_role(session: Session, token: str | None, requested_role: str | None) -> str:
    """
    Determine whether a connecting WebSocket client is a "moderator" (the
    authenticated owner of this session, or a super admin), a "screen"
    (read-only projector view), or a plain "guest" (audience member).

    Opens and closes its own short-lived DB session rather than depending on
    a request-scoped one, so we never hold a pooled connection open for the
    full lifetime of a WebSocket (a single session can have dozens of
    concurrent audience sockets).
    """
    if token:
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            user_id = payload.get("sub")
            if user_id:
                async with async_session() as db:
                    result = await db.execute(
                        select(User).where(User.id == uuid.UUID(user_id))
                    )
                    user = result.scalar_one_or_none()
                    if user is not None and user.is_active and (
                        user.role == UserRole.SUPER_ADMIN or session.owner_id == user.id
                    ):
                        return "moderator"
        except (JWTError, ValueError):
            pass
    if requested_role == "screen":
        return "screen"
    return "guest"


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
            # Shared pubsub listener — started once per session, not per
            # socket. _listen owns subscribing (and re-subscribing) itself,
            # so a failure there can never leave this freshly-registered
            # bucket orphaned with no task watching it — see _listen.
            task = asyncio.create_task(
                self._listen(session_code, redis),
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
        # Serialise once, fan out to every socket concurrently. Sending
        # sequentially here meant one slow/stalled client's socket write
        # (network backpressure, dead TCP peer not yet detected) delayed
        # delivery to every other socket behind it in the loop — with
        # hundreds of guests per session that turned into multi-second
        # broadcast tails. A bounded per-send timeout guarantees one bad
        # socket can't hold up the round at all.
        payload = json.dumps(message)
        sockets = list(bucket)

        async def _send(ws: WebSocket) -> WebSocket | None:
            try:
                await asyncio.wait_for(ws.send_text(payload), timeout=5.0)
                return None
            except Exception:
                return ws

        dead = await asyncio.gather(*(_send(ws) for ws in sockets))
        for ws in dead:
            if ws is not None:
                await self.disconnect(session_code, ws)

    async def _listen(self, session_code: str, redis: Redis) -> None:
        """Owns this session's shared Redis pubsub subscription end to end,
        including subscribing in the first place — so a subscribe failure
        (transient Redis blip, connection drop) never leaves `connect()`'s
        freshly-registered `_connections[session_code]` bucket orphaned with
        no listener watching it. Retries with backoff for as long as the
        session still has connected sockets, so recovery never requires a
        process restart."""
        channel = f"session:{session_code}"
        delay = 1.0
        while session_code in self._connections:
            pubsub = redis.pubsub()
            try:
                await pubsub.subscribe(channel)
                delay = 1.0  # reset backoff after a successful (re)subscribe
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
                raise
            except Exception as exc:
                logger.warning(
                    "ws_pubsub_error session=%s error=%s — retrying in %.1fs",
                    session_code, exc, delay,
                )
                await asyncio.sleep(delay)
                delay = min(delay * 2, 30.0)
            finally:
                try:
                    await pubsub.unsubscribe(channel)
                except Exception:
                    pass


manager = ConnectionManager()


@router.websocket("/ws/{session_code}")
async def websocket_endpoint(websocket: WebSocket, session_code: str):
    redis: Redis = websocket.app.state.redis

    client_host = websocket.client.host if websocket.client else "unknown"
    # Scoped by (IP, session code), matching the join endpoint's rationale
    # (app/routers/sessions.py::join_session): a shared venue/NAT IP running
    # one large workshop gets that session's full connect-burst budget
    # without bleeding into or being starved by an unrelated session behind
    # the same IP. Keyed on the raw path param, before the existence check
    # below, so this stays a cheap pre-check with no DB round-trip.
    allowed = await check_rate_limit(
        redis,
        f"rate:ws_connect:{client_host}:{session_code}",
        settings.WS_CONNECT_RATE_LIMIT,
        settings.WS_CONNECT_RATE_WINDOW_SECONDS,
    )
    if not allowed:
        await websocket.close(code=4429)
        return

    # Validate the session exists BEFORE accepting/subscribing — an
    # unauthenticated client must not be able to open a Redis pubsub
    # subscription for an arbitrary or nonexistent session_code.
    session = await _get_session_by_code(session_code)
    if session is None:
        await websocket.close(code=4404)
        return

    role = await resolve_ws_role(
        session,
        websocket.query_params.get("token"),
        websocket.query_params.get("role"),
    )
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
                event = message.get("event")
                # Drop unknown event types to prevent UI injection by guests
                if event not in ALLOWED_WS_EVENTS:
                    continue
                # Only the session's moderator (or an admin) may relay control events —
                # guests can only submit responses (via the HTTP API), and screens are
                # strictly read-only.
                if event in MODERATOR_ONLY_EVENTS and role != "moderator":
                    logger.warning(
                        "Rejected unauthorized WS event '%s' from role=%s session=%s",
                        event, role, session_code,
                    )
                    await websocket.send_text(json.dumps({
                        "event": "error",
                        "message": f"Unauthorized: '{event}' requires moderator role",
                    }))
                    continue
                message.setdefault("origin", SERVER_ID)
                await manager.broadcast(session_code, message)
                # Local sockets already got the broadcast above — a Redis
                # publish failure here only means OTHER app processes miss
                # this relay, not that this connection is broken. Fails open
                # (logged, not re-raised) so a transient Redis blip doesn't
                # trip the broad `except Exception` below and drop this
                # client's entire WebSocket connection over one lost relay.
                try:
                    await redis.publish(f"session:{session_code}", json.dumps(message))
                except RedisError:
                    logger.warning(
                        "ws_relay_publish_failed session=%s event=%s",
                        session_code, event, exc_info=True,
                    )
            except WebSocketDisconnect:
                break
            except Exception:
                logger.exception("WebSocket handler error for session %s", session_code)
                break
    finally:
        await manager.disconnect(session_code, websocket)
