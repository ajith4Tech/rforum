"""
Tests for server-side pagination on GET /api/events and GET /api/sessions
(app/routers/events.py::list_events, app/routers/sessions.py::list_sessions).

Verifies: default page size, limit/offset, response envelope shape
(items/total/limit/offset/has_more), newest-first ordering, permission
scoping is preserved, and search filtering works alongside pagination.

Same dedicated 'rforum_test' Postgres database convention as the other
test_*.py files here. The main 'rforum' dev database is never touched.
"""
import os
import uuid
from datetime import date, timedelta

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
            f"Postgres not reachable at localhost:5433 — skipping pagination tests: {check.stderr.strip()}",
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

    user = User(email="pagination-owner@example.com", hashed_password="x", role="USER")
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture(loop_scope="session")
async def other_user(db):
    from app.models import User

    user = User(email="pagination-other@example.com", hashed_password="x", role="USER")
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture(loop_scope="session")
async def admin_user(db):
    from app.models import User

    user = User(email="pagination-admin@example.com", hashed_password="x", role="SUPER_ADMIN")
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture(loop_scope="session")
async def owner_events(db, owner_user):
    """25 events for owner_user, event_date ascending so event_date DESC
    ordering is unambiguous (event[0] is oldest, event[24] is newest)."""
    from app.models import Event

    events = []
    base = date(2026, 1, 1)
    for i in range(25):
        event = Event(
            owner_id=owner_user.id,
            title=f"Owner Event {i:02d}",
            event_date=base + timedelta(days=i),
            description="Keynote and workshops" if i == 5 else None,
        )
        db.add(event)
        events.append(event)
    await db.commit()
    for event in events:
        await db.refresh(event)
    return events


@pytest_asyncio.fixture(loop_scope="session")
async def other_event(db, other_user):
    from app.models import Event

    event = Event(owner_id=other_user.id, title="Other User's Event", event_date=date(2026, 6, 1))
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return event


@pytest_asyncio.fixture(loop_scope="session")
async def owner_sessions(db, owner_user, owner_events):
    """25 sessions for owner_user, one with a distinctive moderator name for
    search testing. created_at is set explicitly (increasing) rather than
    relying on the server_default — inserted together in one transaction,
    every row would otherwise get Postgres's transaction-start now(), tying
    created_at DESC ordering."""
    from app.models import Session
    from datetime import datetime, timezone

    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    sessions = []
    for i in range(25):
        session = Session(
            owner_id=owner_user.id,
            unique_code=f"P{uuid.uuid4().hex[:8].upper()}",
            title=f"Owner Session {i:02d}",
            moderator_name="Ada Lovelace" if i == 3 else None,
            created_at=base + timedelta(minutes=i),
        )
        db.add(session)
        sessions.append(session)
    await db.commit()
    for session in sessions:
        await db.refresh(session)
    return sessions


@pytest_asyncio.fixture(loop_scope="session")
async def other_session(db, other_user):
    from app.models import Session

    session = Session(
        owner_id=other_user.id,
        unique_code=f"O{uuid.uuid4().hex[:8].upper()}",
        title="Other User's Session",
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


@pytest_asyncio.fixture(loop_scope="session")
async def presentation_for_search(db, owner_user):
    from app.models import Presentation, PresentationSourceFormat, PresentationStatus

    pres = Presentation(
        owner_id=owner_user.id,
        original_file_name="Quarterly-Roadmap.pdf",
        original_file_url="pagination/roadmap.pdf",
        original_file_type="application/pdf",
        source_format=PresentationSourceFormat.PDF,
        status=PresentationStatus.READY,
        page_count=1,
    )
    db.add(pres)
    await db.commit()
    await db.refresh(pres)
    return pres


@pytest_asyncio.fixture(loop_scope="session")
async def owner_session_with_presentation(db, owner_user, presentation_for_search):
    from app.models import Session

    session = Session(
        owner_id=owner_user.id,
        unique_code=f"Q{uuid.uuid4().hex[:8].upper()}",
        title="Session With Deck",
        presentation_id=presentation_for_search.id,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


def _token_for(user):
    from app.auth import create_access_token

    return create_access_token(user.id)


class _FakeRedis:
    async def publish(self, *args, **kwargs):
        pass

    async def incr(self, key):
        return 1

    async def expire(self, key, seconds):
        pass


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


class TestEventsPagination:
    async def test_default_page_size_is_twenty(self, client, owner_user, owner_events):
        resp = await client.get("/api/events/", headers={"Authorization": f"Bearer {_token_for(owner_user)}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["limit"] == 20
        assert data["offset"] == 0
        assert data["total"] == 25
        assert len(data["items"]) == 20
        assert data["has_more"] is True

    async def test_second_page_via_offset(self, client, owner_user, owner_events):
        resp = await client.get(
            "/api/events/", params={"limit": 20, "offset": 20},
            headers={"Authorization": f"Bearer {_token_for(owner_user)}"},
        )
        data = resp.json()
        assert data["total"] == 25
        assert len(data["items"]) == 5
        assert data["has_more"] is False

    async def test_custom_limit(self, client, owner_user, owner_events):
        resp = await client.get(
            "/api/events/", params={"limit": 5},
            headers={"Authorization": f"Bearer {_token_for(owner_user)}"},
        )
        data = resp.json()
        assert len(data["items"]) == 5
        assert data["has_more"] is True

    async def test_limit_is_clamped_to_max_page_size(self, client, owner_user, owner_events):
        resp = await client.get(
            "/api/events/", params={"limit": 99999},
            headers={"Authorization": f"Bearer {_token_for(owner_user)}"},
        )
        data = resp.json()
        assert data["limit"] == 100  # settings.MAX_PAGE_SIZE

    async def test_newest_first_ordering(self, client, owner_user, owner_events):
        resp = await client.get(
            "/api/events/", params={"limit": 3},
            headers={"Authorization": f"Bearer {_token_for(owner_user)}"},
        )
        titles = [e["title"] for e in resp.json()["items"]]
        assert titles == ["Owner Event 24", "Owner Event 23", "Owner Event 22"]

    async def test_permission_scoping_preserved(self, client, other_user, other_event, owner_events):
        resp = await client.get("/api/events/", headers={"Authorization": f"Bearer {_token_for(other_user)}"})
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["title"] == "Other User's Event"

    async def test_admin_sees_all_events(self, client, admin_user, owner_events, other_event):
        resp = await client.get(
            "/api/events/", params={"limit": 100},
            headers={"Authorization": f"Bearer {_token_for(admin_user)}"},
        )
        data = resp.json()
        assert data["total"] == 26  # 25 owner + 1 other

    async def test_search_by_title(self, client, owner_user, owner_events):
        resp = await client.get(
            "/api/events/", params={"search": "Event 05"},
            headers={"Authorization": f"Bearer {_token_for(owner_user)}"},
        )
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["title"] == "Owner Event 05"

    async def test_search_by_description(self, client, owner_user, owner_events):
        resp = await client.get(
            "/api/events/", params={"search": "keynote"},
            headers={"Authorization": f"Bearer {_token_for(owner_user)}"},
        )
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["title"] == "Owner Event 05"

    async def test_search_resets_pagination_math_correctly(self, client, owner_user, owner_events):
        resp = await client.get(
            "/api/events/", params={"search": "nonexistent-xyz"},
            headers={"Authorization": f"Bearer {_token_for(owner_user)}"},
        )
        data = resp.json()
        assert data["total"] == 0
        assert data["items"] == []
        assert data["has_more"] is False


class TestSessionsPagination:
    async def test_default_page_size_is_twenty(self, client, owner_user, owner_sessions):
        resp = await client.get("/api/sessions/", headers={"Authorization": f"Bearer {_token_for(owner_user)}"})
        data = resp.json()
        assert data["limit"] == 20
        assert data["total"] == 25
        assert len(data["items"]) == 20
        assert data["has_more"] is True

    async def test_second_page_via_offset(self, client, owner_user, owner_sessions):
        resp = await client.get(
            "/api/sessions/", params={"limit": 20, "offset": 20},
            headers={"Authorization": f"Bearer {_token_for(owner_user)}"},
        )
        data = resp.json()
        assert len(data["items"]) == 5
        assert data["has_more"] is False

    async def test_newest_first_ordering(self, client, owner_user, owner_sessions):
        resp = await client.get(
            "/api/sessions/", params={"limit": 3},
            headers={"Authorization": f"Bearer {_token_for(owner_user)}"},
        )
        titles = [s["title"] for s in resp.json()["items"]]
        assert titles == ["Owner Session 24", "Owner Session 23", "Owner Session 22"]

    async def test_permission_scoping_preserved(self, client, other_user, other_session, owner_sessions):
        resp = await client.get("/api/sessions/", headers={"Authorization": f"Bearer {_token_for(other_user)}"})
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["title"] == "Other User's Session"

    async def test_search_by_moderator_name(self, client, owner_user, owner_sessions):
        resp = await client.get(
            "/api/sessions/", params={"search": "Lovelace"},
            headers={"Authorization": f"Bearer {_token_for(owner_user)}"},
        )
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["title"] == "Owner Session 03"

    async def test_search_by_unique_code(self, client, owner_user, owner_sessions):
        target = owner_sessions[10]
        resp = await client.get(
            "/api/sessions/", params={"search": target.unique_code},
            headers={"Authorization": f"Bearer {_token_for(owner_user)}"},
        )
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["id"] == str(target.id)

    async def test_search_by_attached_presentation_filename(
        self, client, owner_user, owner_session_with_presentation, owner_sessions
    ):
        resp = await client.get(
            "/api/sessions/", params={"search": "Quarterly-Roadmap"},
            headers={"Authorization": f"Bearer {_token_for(owner_user)}"},
        )
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["title"] == "Session With Deck"
