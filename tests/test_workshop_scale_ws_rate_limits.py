"""
WebSocket-connect half of the 500-guest-workshop rate-limit fix (see
tests/test_workshop_scale_rate_limits.py for the join/response half).

Kept in its OWN file, deliberately with no `pytest.mark.asyncio` module mark,
because it uses FastAPI's synchronous TestClient for WebSocket support
(websocket_connect has no async equivalent in this codebase's dependencies —
same reasoning as tests/test_ws_auth.py). Mixing that sync pattern into a
module marked `pytestmark = pytest.mark.asyncio(loop_scope="session")`
(as tests/test_workshop_scale_rate_limits.py's async HTTP tests need) made
these tests order-dependent and occasionally error out when run after an
async test in the same session-scoped event loop — splitting the file is
what test_ws_auth.py already does for the same reason, so this follows that
existing convention instead of introducing a new one.

Same dedicated 'rforum_test' Postgres database convention as
test_ws_auth.py / test_endpoint_hardening.py. The main 'rforum' dev database
is never touched.
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
            f"Postgres not reachable at localhost:5433 — skipping workshop-scale WS rate-limit tests: "
            f"{check.stderr.strip()}",
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
        owner = User(email=f"workshop-ws-owner-{uuid.uuid4().hex[:8]}@example.com", hashed_password="x", role="USER")
        db.add(owner)
        await db.commit()
        await db.refresh(owner)

        session_a = Session(
            owner_id=owner.id, unique_code=f"W{uuid.uuid4().hex[:8].upper()}",
            title="500-Guest Workshop (WS)", is_live=True,
        )
        session_b = Session(
            owner_id=owner.id, unique_code=f"V{uuid.uuid4().hex[:8].upper()}",
            title="Unrelated Second Session (WS)", is_live=True,
        )
        db.add_all([session_a, session_b])
        await db.commit()
        await db.refresh(session_a)
        await db.refresh(session_b)

        ids = {"owner_id": owner.id, "session_a_id": session_a.id, "session_b_id": session_b.id}
        codes = (session_a.unique_code, session_b.unique_code)

    await engine.dispose()
    return ids, codes


async def _cleanup(ids):
    from app.models import Session, User

    engine = create_async_engine(TEST_DATABASE_URL)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as db:
        await db.execute(delete(Session).where(Session.id.in_([ids["session_a_id"], ids["session_b_id"]])))
        await db.execute(delete(User).where(User.id == ids["owner_id"]))
        await db.commit()
    await engine.dispose()


@pytest.fixture
def seeded():
    ids, codes = _run(_seed())
    yield codes
    _run(_cleanup(ids))


class _FakePubSub:
    """Mimics just enough of redis.asyncio's PubSub for
    ConnectionManager._listen (app/routers/ws.py) to subscribe and then block
    "forever" — same shape as test_ws_auth.py's TestPubsubSubscriptionRecovery
    fixture, reused here so the listener task doesn't die with an unhandled
    AttributeError on every connect (harmless to test outcomes, but noisy)."""

    async def subscribe(self, channel):
        pass

    async def listen(self):
        await asyncio.Event().wait()
        if False:
            yield  # pragma: no cover — makes this an async generator

    async def unsubscribe(self, channel):
        pass


class _FakeRedis:
    """Deterministic incr/expire counter, isolated from whatever a real
    Redis instance might already hold for a given key."""

    def __init__(self):
        self._counts: dict[str, int] = {}

    async def incr(self, key):
        self._counts[key] = self._counts.get(key, 0) + 1
        return self._counts[key]

    async def expire(self, key, seconds):
        pass

    def pubsub(self):
        return _FakePubSub()

    async def close(self):
        pass

    async def aclose(self):
        pass


@pytest.fixture
def ws_client(monkeypatch):
    from app.main import app
    import app.routers.ws as ws_module

    test_engine = create_async_engine(TEST_DATABASE_URL)
    factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(ws_module, "async_session", factory)

    with TestClient(app) as client:
        client.app.state.redis = _FakeRedis()
        yield client

    _run(test_engine.dispose())


class TestWsConnectBurstAndIsolation:
    """The Phase 3 equivalent of Test500GuestJoinBurst: ~500 guests, one
    shared IP (TestClient uses one fixed test client address for every
    connection), one session — must all be allowed under the default
    WS_CONNECT_RATE_LIMIT, and a second unrelated session behind the same IP
    must not share that budget."""

    def test_500_ws_connects_to_the_same_session_from_one_ip_all_succeed(self, ws_client, seeded):
        code_a, _code_b = seeded
        for _ in range(500):
            with ws_client.websocket_connect(f"/ws/{code_a}"):
                pass  # accepted (would raise WebSocketDisconnect on a 4429/4404 reject)

    def test_exhausting_one_sessions_ws_budget_does_not_affect_another(self, ws_client, monkeypatch, seeded):
        import app.routers.ws as ws_module

        code_a, code_b = seeded
        monkeypatch.setattr(
            ws_module, "settings",
            ws_module.settings.model_copy(update={"WS_CONNECT_RATE_LIMIT": 3}),
        )

        for _ in range(3):
            with ws_client.websocket_connect(f"/ws/{code_a}"):
                pass

        with pytest.raises(WebSocketDisconnect) as exc_info:
            with ws_client.websocket_connect(f"/ws/{code_a}"):
                pass
        assert exc_info.value.code == 4429

        # Different session, same IP — must connect fine, not 4429.
        with ws_client.websocket_connect(f"/ws/{code_b}"):
            pass

    def test_excessive_ws_abuse_beyond_the_limit_is_still_rejected(self, ws_client, monkeypatch, seeded):
        import app.routers.ws as ws_module

        code_a, _code_b = seeded
        monkeypatch.setattr(
            ws_module, "settings",
            ws_module.settings.model_copy(update={"WS_CONNECT_RATE_LIMIT": 5}),
        )
        for _ in range(5):
            with ws_client.websocket_connect(f"/ws/{code_a}"):
                pass
        for _ in range(3):
            with pytest.raises(WebSocketDisconnect) as exc_info:
                with ws_client.websocket_connect(f"/ws/{code_a}"):
                    pass
            assert exc_info.value.code == 4429
