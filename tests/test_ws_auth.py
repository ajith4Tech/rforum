"""
Integration tests for the WebSocket moderator/guest/screen role separation in
app/routers/ws.py, against a real (dedicated) Postgres test database — same
'rforum_test' database test_presentations.py uses, see docker-compose.yml.
The main 'rforum' dev database is never touched.

Uses FastAPI's synchronous TestClient for WebSocket support (websocket_connect
has no async equivalent in this codebase's dependencies). All async DB setup/
teardown for each test runs to completion via asyncio.run() *before* the
synchronous TestClient block starts, and app.routers.ws's module-level
`async_session` is monkeypatched to a sessionmaker bound to the test engine —
so no asyncpg connection is ever shared across two different event loops.
"""
import asyncio
import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from starlette.websockets import WebSocketDisconnect

os.environ.setdefault("STORAGE_BACKEND", "local")

TEST_DATABASE_URL = "postgresql+asyncpg://rforum:rforum@localhost:5433/rforum_test"


def _require_test_postgres():
    import subprocess

    env = {**os.environ, "PGPASSWORD": "rforum"}
    check = subprocess.run(
        ["psql", "-h", "localhost", "-p", "5433", "-U", "rforum", "-d", "rforum", "-tAc",
         "SELECT 1 FROM pg_database WHERE datname = 'rforum_test'"],
        capture_output=True, text=True, env=env,
    )
    if check.returncode != 0:
        pytest.skip(
            f"Postgres not reachable at localhost:5433 — skipping WS auth tests: {check.stderr.strip()}",
            allow_module_level=True,
        )
        return
    if check.stdout.strip() != "1":
        subprocess.run(
            ["createdb", "-h", "localhost", "-p", "5433", "-U", "rforum", "rforum_test"],
            env=env, check=True,
        )


_require_test_postgres()


def _run(coro):
    return asyncio.run(coro)


async def _seed():
    from app.database import Base
    from app.models import Session, User

    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as db:
        owner = User(email=f"ws-owner-{uuid.uuid4().hex[:8]}@example.com", hashed_password="x", role="USER")
        other = User(email=f"ws-other-{uuid.uuid4().hex[:8]}@example.com", hashed_password="x", role="USER")
        db.add_all([owner, other])
        await db.commit()
        await db.refresh(owner)
        await db.refresh(other)

        session = Session(
            owner_id=owner.id,
            unique_code=f"W{uuid.uuid4().hex[:8].upper()}",
            title="WS Auth Test Session",
        )
        db.add(session)
        await db.commit()
        await db.refresh(session)

        ids = {"owner_id": owner.id, "other_id": other.id, "session_id": session.id}
        code = session.unique_code

    await engine.dispose()
    return ids, code


async def _cleanup(ids):
    from app.models import Session, User

    engine = create_async_engine(TEST_DATABASE_URL)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as db:
        await db.execute(delete(Session).where(Session.id == ids["session_id"]))
        await db.execute(delete(User).where(User.id.in_([ids["owner_id"], ids["other_id"]])))
        await db.commit()
    await engine.dispose()


@pytest.fixture
def seeded():
    ids, code = _run(_seed())
    yield ids, code
    _run(_cleanup(ids))


@pytest.fixture
def ws_client(monkeypatch):
    from app.main import app
    import app.routers.ws as ws_module

    test_engine = create_async_engine(TEST_DATABASE_URL)
    factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(ws_module, "async_session", factory)

    with TestClient(app) as client:
        yield client

    _run(test_engine.dispose())


def _owner_token(ids):
    from app.auth import create_access_token

    return create_access_token(ids["owner_id"])


def _other_token(ids):
    from app.auth import create_access_token

    return create_access_token(ids["other_id"])


class TestModeratorOnlyEvents:
    """slide_change / page_change / session_update require role == moderator."""

    def test_guest_cannot_send_slide_change(self, ws_client, seeded):
        ids, code = seeded
        with ws_client.websocket_connect(f"/ws/{code}") as guest_ws:
            guest_ws.send_json({"event": "slide_change", "data": {"slide_id": "x"}})
            reply = guest_ws.receive_json()
            assert reply["event"] == "error"
            assert "moderator" in reply["message"].lower()

    def test_screen_cannot_send_session_update(self, ws_client, seeded):
        ids, code = seeded
        with ws_client.websocket_connect(f"/ws/{code}?role=screen") as screen_ws:
            screen_ws.send_json({"event": "session_update", "data": {"is_live": True}})
            reply = screen_ws.receive_json()
            assert reply["event"] == "error"
            assert "moderator" in reply["message"].lower()

    def test_token_for_a_different_users_session_is_treated_as_guest(self, ws_client, seeded):
        ids, code = seeded
        with ws_client.websocket_connect(f"/ws/{code}?token={_other_token(ids)}") as not_owner_ws:
            not_owner_ws.send_json({"event": "page_change", "data": {"file_page": 2}})
            reply = not_owner_ws.receive_json()
            assert reply["event"] == "error"

    def test_moderator_can_broadcast_slide_change_to_a_guest(self, ws_client, seeded):
        ids, code = seeded
        with ws_client.websocket_connect(f"/ws/{code}") as guest_ws:
            with ws_client.websocket_connect(f"/ws/{code}?token={_owner_token(ids)}") as moderator_ws:
                moderator_ws.send_json({"event": "slide_change", "data": {"slide_id": "abc"}})
                received = guest_ws.receive_json()
                assert received["event"] == "slide_change"
                assert received["data"]["slide_id"] == "abc"

    def test_moderator_can_send_all_three_control_events(self, ws_client, seeded):
        ids, code = seeded
        with ws_client.websocket_connect(f"/ws/{code}") as guest_ws:
            with ws_client.websocket_connect(f"/ws/{code}?token={_owner_token(ids)}") as moderator_ws:
                for event in ("slide_change", "page_change", "session_update"):
                    moderator_ws.send_json({"event": event, "data": {}})
                    received = guest_ws.receive_json()
                    assert received["event"] == event


class TestNonexistentSessionCodeRejected:
    """A WS connect for a session_code that doesn't exist must be rejected
    before manager.connect() ever subscribes to Redis — see
    app/routers/ws.py::websocket_endpoint's existence check."""

    def test_connect_to_unknown_code_is_disconnected(self, ws_client):
        with pytest.raises(WebSocketDisconnect):
            with ws_client.websocket_connect("/ws/DOES-NOT-EXIST"):
                pass


class TestUnrestrictedEventsUnchanged:
    """Non-control events (heartbeat etc.) are still broadcastable by anyone — no regression."""

    def test_guest_heartbeat_still_broadcasts_and_unknown_event_is_still_silently_dropped(self, ws_client, seeded):
        ids, code = seeded
        with ws_client.websocket_connect(f"/ws/{code}") as sender_ws, \
                ws_client.websocket_connect(f"/ws/{code}") as receiver_ws:
            # Unknown event type: dropped with no reply and no broadcast (existing behavior).
            sender_ws.send_json({"event": "totally_unknown_event", "data": {}})
            # A known, unrestricted event sent right after it.
            sender_ws.send_json({"event": "heartbeat", "data": {}})
            received = receiver_ws.receive_json()
            assert received["event"] == "heartbeat"


class TestPubsubSubscriptionRecovery:
    """ConnectionManager._listen owns subscribing (and re-subscribing)
    itself, so a subscribe failure — the very first attempt, or a connection
    drop mid-listen — retries with backoff instead of permanently leaving a
    session's cross-process relay dead until a process restart."""

    def test_first_subscribe_failure_is_retried_and_recovers(self):
        import app.routers.ws as ws_module

        async def scenario():
            manager = ws_module.ConnectionManager()
            session_code = "RETRY-TEST"
            # Stands in for a connected websocket — only its truthiness in
            # `self._connections` matters to keep _listen's retry loop alive.
            manager._connections[session_code] = {object()}

            attempts = {"n": 0}

            class FakePubSub:
                async def subscribe(self, channel):
                    attempts["n"] += 1
                    if attempts["n"] == 1:
                        raise ConnectionError("simulated Redis blip")

                async def listen(self):
                    # Blocks "forever" once subscribed, until the task is cancelled.
                    await asyncio.Event().wait()
                    if False:
                        yield  # pragma: no cover — makes this an async generator

                async def unsubscribe(self, channel):
                    pass

            class FakeRedis:
                def pubsub(self):
                    return FakePubSub()

            task = asyncio.create_task(manager._listen(session_code, FakeRedis()))
            try:
                # First (failing) attempt runs immediately; the retried
                # attempt fires after the ~1s backoff — give it enough room.
                await asyncio.sleep(1.3)
                assert attempts["n"] == 2
            finally:
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task

        asyncio.run(scenario())
