"""
Coverage for the 500-guest-workshop rate-limit fix — join and response
endpoints (see tests/test_workshop_scale_ws_rate_limits.py for the
WebSocket-connect half, kept in its own file for reasons explained there):

  - JOIN_RATE_LIMIT / WS_CONNECT_RATE_LIMIT / RESPONSE_RATE_LIMIT_PER_IP were
    raised to 600/60s (app/config.py) to comfortably cover a single live
    workshop's ~500-guest burst with headroom.
  - The join and WS-connect rate-limit keys are now scoped by
    (client IP, session code) instead of client IP alone (app/routers/
    sessions.py::join_session, app/routers/ws.py::websocket_endpoint), so a
    shared-NAT audience's budget is isolated per session rather than shared
    globally across every session that IP happens to touch. The response
    endpoint's per-IP key was already scoped per slide_id — no key change
    needed there, just the limit increase.
  - app/routers/responses.py's rate limiting now goes through the shared
    check_rate_limit() helper (app/rate_limit.py) instead of a hand-rolled
    incr/expire pair that had no Redis-error handling — a transient Redis
    outage during response submission used to become a hard 500 instead of
    failing open like the join/WS-connect checks already did.

Same dedicated 'rforum_test' Postgres database convention as
test_endpoint_hardening.py / test_legacy_compatibility.py. The main 'rforum'
dev database is never touched.
"""
import os
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

pytestmark = pytest.mark.asyncio(loop_scope="session")

os.environ.setdefault("STORAGE_BACKEND", "local")

TEST_DATABASE_URL = "postgresql+asyncpg://rforum:rforum@localhost:5433/rforum_test"

# DATABASE_URL/SECRET_KEY/INVITE_CODE/CORS_ORIGINS have no insecure default
# (app/config.py) and must be supplied explicitly whenever a test builds a
# Settings() with _env_file=None.
_REQUIRED_SETTINGS = dict(
    DATABASE_URL=TEST_DATABASE_URL,
    SECRET_KEY="test-secret-key",
    INVITE_CODE="TEST-CODE",
    CORS_ORIGINS=["http://testserver"],
)


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
            f"Postgres not reachable at localhost:5433 — skipping workshop-scale rate-limit tests: "
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


# ── DB fixtures ─────────────────────────────────────────────────────────────

@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def test_engine():
    from app.database import Base

    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(loop_scope="session")
async def db(test_engine):
    from app.database import Base

    async_session = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session

    import asyncpg

    conn = await asyncpg.connect(TEST_DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://"))
    try:
        table_names = ", ".join(t.name for t in Base.metadata.sorted_tables)
        await conn.execute(f"TRUNCATE TABLE {table_names} CASCADE")
    finally:
        await conn.close()


@pytest_asyncio.fixture(loop_scope="session")
async def owner_user(db):
    from app.models import User

    user = User(email=f"workshop-owner-{uuid.uuid4().hex[:8]}@example.com", hashed_password="x", role="USER")
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture(loop_scope="session")
async def live_session(db, owner_user):
    """The one active workshop session all 500 simulated guests target."""
    from app.models import Session

    session = Session(
        owner_id=owner_user.id,
        unique_code=f"W{uuid.uuid4().hex[:8].upper()}",
        title="500-Guest Workshop",
        is_live=True,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


@pytest_asyncio.fixture(loop_scope="session")
async def second_live_session(db, owner_user):
    """An unrelated second session, same owner, behind the SAME test IP —
    used to prove join/WS rate limits are scoped per session, not globally
    per IP."""
    from app.models import Session

    session = Session(
        owner_id=owner_user.id,
        unique_code=f"V{uuid.uuid4().hex[:8].upper()}",
        title="Unrelated Second Session",
        is_live=True,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


@pytest_asyncio.fixture(loop_scope="session")
async def active_slide(db, live_session):
    from app.models import Slide

    slide = Slide(
        session_id=live_session.id,
        type="POLL",
        order=0,
        content_json={"question": "Workshop poll?", "options": ["A", "B", "C", "D"]},
        is_active=True,
    )
    db.add(slide)
    await db.commit()
    await db.refresh(slide)
    return slide


# ── HTTP client (join / response endpoints) ──────────────────────────────────

class _FakeRedis:
    """In-memory incr/expire/publish stand-in — deterministic counters, no
    dependency on a real Redis instance being reachable. Each test gets a
    fresh instance via the `client`/`ws_client` fixtures below, so counts
    never leak between tests."""

    def __init__(self):
        self._counts: dict[str, int] = {}

    async def publish(self, *args, **kwargs):
        pass

    async def incr(self, key):
        self._counts[key] = self._counts.get(key, 0) + 1
        return self._counts[key]

    async def expire(self, key, seconds):
        pass

    async def close(self):
        pass

    async def aclose(self):
        pass


class _FailingRedis:
    """Every call raises, simulating a Redis outage — used to prove the
    fail-open contract holds end-to-end through the actual HTTP endpoints,
    not just at the check_rate_limit() unit level."""

    async def publish(self, *args, **kwargs):
        pass

    async def incr(self, key):
        from redis.exceptions import ConnectionError as RedisConnectionError
        raise RedisConnectionError("simulated Redis outage")

    async def expire(self, key, seconds):
        from redis.exceptions import ConnectionError as RedisConnectionError
        raise RedisConnectionError("simulated Redis outage")


@pytest_asyncio.fixture(loop_scope="session")
async def client(db, test_engine):
    from app.database import get_db
    from app.main import app

    request_session_factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db():
        async with request_session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    app.state.redis = _FakeRedis()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


# ── PHASE 2 equivalent: join burst ───────────────────────────────────────────

class Test500GuestJoinBurst:
    """The exact scenario the load test runs: ~500 guests, one shared IP
    (all requests come from the same AsyncClient/ASGITransport pair, which
    httpx gives a single fixed client address), one session."""

    async def test_500_joins_to_the_same_session_from_one_ip_all_succeed(self, client, live_session):
        statuses = []
        for _ in range(500):
            resp = await client.get(f"/api/sessions/join/{live_session.unique_code}")
            statuses.append(resp.status_code)

        assert all(s == 200 for s in statuses), (
            f"expected all 500 joins to succeed under the default JOIN_RATE_LIMIT, "
            f"got statuses: {sorted(set(statuses))}"
        )


class TestJoinRateLimitIsSessionScoped:
    """Different session codes must not share a join budget — a small
    monkeypatched limit makes this fast and deterministic."""

    async def test_exhausting_one_sessions_join_budget_does_not_affect_another(
        self, client, monkeypatch, live_session, second_live_session
    ):
        import app.routers.sessions as sessions_module
        from app.config import Settings

        monkeypatch.setattr(
            sessions_module, "get_settings",
            lambda: Settings(_env_file=None, **_REQUIRED_SETTINGS, JOIN_RATE_LIMIT=3, JOIN_RATE_LIMIT_WINDOW_SECONDS=60),
        )

        # Exhaust session A's budget (3 allowed, 4th rejected).
        for _ in range(3):
            resp = await client.get(f"/api/sessions/join/{live_session.unique_code}")
            assert resp.status_code == 200
        resp = await client.get(f"/api/sessions/join/{live_session.unique_code}")
        assert resp.status_code == 429

        # Session B, same IP, fresh budget — must NOT be 429.
        resp = await client.get(f"/api/sessions/join/{second_live_session.unique_code}")
        assert resp.status_code == 200

    async def test_excessive_abuse_beyond_the_limit_is_still_rejected(self, client, monkeypatch, live_session):
        import app.routers.sessions as sessions_module
        from app.config import Settings

        monkeypatch.setattr(
            sessions_module, "get_settings",
            lambda: Settings(_env_file=None, **_REQUIRED_SETTINGS, JOIN_RATE_LIMIT=5, JOIN_RATE_LIMIT_WINDOW_SECONDS=60),
        )
        for _ in range(5):
            resp = await client.get(f"/api/sessions/join/{live_session.unique_code}")
            assert resp.status_code == 200
        for _ in range(3):
            resp = await client.get(f"/api/sessions/join/{live_session.unique_code}")
            assert resp.status_code == 429


class TestJoinRedisOutageFailsOpen:
    async def test_join_succeeds_when_redis_is_unreachable(self, client, live_session):
        from app.main import app

        app.state.redis = _FailingRedis()
        resp = await client.get(f"/api/sessions/join/{live_session.unique_code}")
        assert resp.status_code == 200


# ── PHASE 6 equivalent: response burst ───────────────────────────────────────

class Test500ResponseBurst:
    async def test_500_responses_to_the_same_slide_from_one_ip_all_succeed(self, client, active_slide):
        statuses = []
        for i in range(500):
            resp = await client.post(
                f"/api/slides/{active_slide.id}/responses/",
                json={"value": "A", "guest_identifier": f"guest-{i}", "name": "k6-guest"},
            )
            statuses.append(resp.status_code)

        assert all(s == 201 for s in statuses), (
            f"expected all 500 responses to succeed under the default RESPONSE_RATE_LIMIT_PER_IP, "
            f"got statuses: {sorted(set(statuses))}"
        )


class TestResponseRateLimitStillBlocksAbuse:
    async def test_per_ip_limit_still_rejects_excess_once_exceeded(self, client, monkeypatch, active_slide):
        import app.routers.responses as responses_module
        from app.config import Settings

        monkeypatch.setattr(
            responses_module, "get_settings",
            lambda: Settings(
                _env_file=None,
                **_REQUIRED_SETTINGS,
                RESPONSE_RATE_LIMIT_PER_IP=5, RESPONSE_RATE_LIMIT_PER_IP_WINDOW_SECONDS=60,
                RESPONSE_RATE_LIMIT_PER_GUEST=100, RESPONSE_RATE_LIMIT_PER_GUEST_WINDOW_SECONDS=60,
            ),
        )
        for i in range(5):
            resp = await client.post(
                f"/api/slides/{active_slide.id}/responses/",
                json={"value": "A", "guest_identifier": f"guest-{i}", "name": "g"},
            )
            assert resp.status_code == 201
        resp = await client.post(
            f"/api/slides/{active_slide.id}/responses/",
            json={"value": "A", "guest_identifier": "guest-overflow", "name": "g"},
        )
        assert resp.status_code == 429

    async def test_per_guest_limit_still_rejects_one_guest_spamming_a_single_slide(
        self, client, monkeypatch, active_slide
    ):
        import app.routers.responses as responses_module
        from app.config import Settings

        monkeypatch.setattr(
            responses_module, "get_settings",
            lambda: Settings(
                _env_file=None,
                **_REQUIRED_SETTINGS,
                RESPONSE_RATE_LIMIT_PER_GUEST=3, RESPONSE_RATE_LIMIT_PER_GUEST_WINDOW_SECONDS=60,
                RESPONSE_RATE_LIMIT_PER_IP=1000, RESPONSE_RATE_LIMIT_PER_IP_WINDOW_SECONDS=60,
            ),
        )
        for _ in range(3):
            resp = await client.post(
                f"/api/slides/{active_slide.id}/responses/",
                json={"value": "A", "guest_identifier": "same-guest", "name": "g"},
            )
            assert resp.status_code == 201
        resp = await client.post(
            f"/api/slides/{active_slide.id}/responses/",
            json={"value": "A", "guest_identifier": "same-guest", "name": "g"},
        )
        assert resp.status_code == 429


class TestResponseRedisOutageFailsOpen:
    """Regression coverage for the fix in app/routers/responses.py: this used
    to be a hand-rolled incr/expire with no error handling, so a Redis
    outage would have raised an uncaught RedisError (-> HTTP 500) instead of
    failing open like every other rate-limited endpoint."""

    async def test_response_submission_succeeds_when_redis_is_unreachable(self, client, active_slide):
        from app.main import app

        app.state.redis = _FailingRedis()
        resp = await client.post(
            f"/api/slides/{active_slide.id}/responses/",
            json={"value": "A", "guest_identifier": "guest-during-outage", "name": "g"},
        )
        assert resp.status_code == 201
