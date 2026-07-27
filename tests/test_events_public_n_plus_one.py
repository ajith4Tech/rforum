"""GET /api/events/public/today and /api/events/public build their sessions
payload from Event.sessions (selectinload'd alongside the Event query)
instead of re-querying per event — regression tests for both the query-count
fix and output correctness, against a real (dedicated) rforum_test Postgres
database, same convention as test_presentations.py."""
import datetime as dt
import os
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

pytestmark = pytest.mark.asyncio(loop_scope="session")

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
            f"Postgres not reachable at localhost:5433 — skipping events N+1 tests: {check.stderr.strip()}",
            allow_module_level=True,
        )
        return
    if check.stdout.strip() != "1":
        subprocess.run(
            ["createdb", "-h", "localhost", "-p", "5433", "-U", "rforum", "rforum_test"],
            env=env, check=True,
        )


_require_test_postgres()


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def test_engine():
    from app.database import Base

    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
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

    user = User(email="events-n1-owner@example.com", hashed_password="x", role="USER")
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture(loop_scope="session")
async def three_published_events_with_two_sessions_each(db, owner_user):
    from app.models import Event, Session

    today = dt.date.today()
    events = [
        Event(owner_id=owner_user.id, title=f"Event {i}", event_date=today, is_published=True)
        for i in range(3)
    ]
    db.add_all(events)
    await db.commit()
    for event in events:
        await db.refresh(event)

    for i, event in enumerate(events):
        live = Session(
            owner_id=owner_user.id, event_id=event.id,
            unique_code=f"N1{i}A{uuid.uuid4().hex[:5].upper()}", title=f"Live {i}", is_live=True,
        )
        ended = Session(
            owner_id=owner_user.id, event_id=event.id,
            unique_code=f"N1{i}B{uuid.uuid4().hex[:5].upper()}", title=f"Ended {i}", is_live=False,
        )
        db.add_all([live, ended])
    await db.commit()

    return events


@pytest_asyncio.fixture(loop_scope="session")
async def client(db, test_engine):
    from app.database import get_db
    from app.main import app

    request_session_factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db():
        async with request_session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


def _count_session_table_selects(engine):
    """Context manager-free counter: attaches a SQLAlchemy core event listener
    to `engine.sync_engine` and returns a mutable counter plus a detach
    function, so the test can assert exactly how many separate SELECTs
    touched the sessions table for N events — 1 (the eager load), not N."""
    from sqlalchemy import event

    count = {"n": 0}

    def _before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        if "FROM sessions" in statement or "from sessions" in statement:
            count["n"] += 1

    event.listen(engine.sync_engine, "before_cursor_execute", _before_cursor_execute)

    def detach():
        event.remove(engine.sync_engine, "before_cursor_execute", _before_cursor_execute)

    return count, detach


class TestPublicTodayEventsNPlusOne:
    async def test_sessions_payload_correctness(self, client, three_published_events_with_two_sessions_each):
        resp = await client.get("/api/events/public/today")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 3
        for event_payload in body:
            sessions = event_payload["sessions"]
            assert len(sessions) == 2
            live = next(s for s in sessions if s["is_live"])
            ended = next(s for s in sessions if not s["is_live"])
            assert live["unique_code"] is not None
            assert ended["unique_code"] is None

    async def test_one_query_covers_all_events_sessions_not_one_per_event(
        self, client, test_engine, three_published_events_with_two_sessions_each
    ):
        count, detach = _count_session_table_selects(test_engine)
        try:
            resp = await client.get("/api/events/public/today")
        finally:
            detach()
        assert resp.status_code == 200
        assert len(resp.json()) == 3
        # One batched selectinload query for all 3 events' sessions — not 3
        # (the N+1 pattern _event_sessions_payload's old per-event query had).
        assert count["n"] == 1, f"expected 1 sessions query for 3 events, got {count['n']}"


class TestPublicEventsListingNPlusOne:
    async def test_one_query_covers_all_events_sessions_not_one_per_event(
        self, client, test_engine, three_published_events_with_two_sessions_each
    ):
        count, detach = _count_session_table_selects(test_engine)
        try:
            resp = await client.get("/api/events/public?upcoming=true")
        finally:
            detach()
        assert resp.status_code == 200
        assert len(resp.json()) == 3
        assert count["n"] == 1, f"expected 1 sessions query for 3 events, got {count['n']}"
