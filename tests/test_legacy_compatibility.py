"""
Backward-compatibility coverage for TRUE legacy sessions (presentation_id IS
NULL) against the security-hardening pass in app/routers/presentations.py,
app/routers/slides.py, app/routers/analytics.py, app/routers/ws.py,
app/routers/sessions.py and app/routers/auth.py.

test_endpoint_hardening.py's "legacy slide" fixtures all use sessions with
presentation_id SET — they exercise the legacy Slide-serving code path, but
never a session that has genuinely never had a presentation attached. This
file adds that missing case, plus a presentation-first counterpart for the
same assertions so both architectures are verified side by side, and closes
out the "existing auth"/"PDF export data" checks called for in the
backward-compatibility milestone.

Same dedicated 'rforum_test' Postgres database convention as
test_endpoint_hardening.py / test_presentations.py. The main 'rforum' dev
database is never touched.
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


def _require_test_postgres():
    import subprocess

    env = {**os.environ, "PGPASSWORD": "rforum"}
    check = subprocess.run(
        ["psql", "-h", "localhost", "-p", "5433", "-U", "rforum", "-d", "rforum", "-tAc",
         "SELECT 1 FROM pg_database WHERE datname = 'rforum_test'"],
        capture_output=True, text=True, env=env,
    )
    if check.returncode != 0:
        pytest.skip(f"Postgres not reachable at localhost:5433 — skipping legacy compatibility tests: {check.stderr.strip()}")
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

    user = User(email="legacy-owner@example.com", hashed_password="x", role="USER")
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture(loop_scope="session")
async def other_user(db):
    from app.models import User

    user = User(email="legacy-other@example.com", hashed_password="x", role="USER")
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture(loop_scope="session")
async def legacy_live_session(db, owner_user):
    """A true legacy session — presentation_id was never set."""
    from app.models import Session

    session = Session(
        owner_id=owner_user.id,
        unique_code=f"G{uuid.uuid4().hex[:8].upper()}",
        title="Legacy Live Session",
        is_live=True,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    assert session.presentation_id is None
    return session


@pytest_asyncio.fixture(loop_scope="session")
async def legacy_ended_session(db, owner_user):
    from app.models import Session

    session = Session(
        owner_id=owner_user.id,
        unique_code=f"H{uuid.uuid4().hex[:8].upper()}",
        title="Legacy Ended Session",
        is_live=False,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    assert session.presentation_id is None
    return session


@pytest_asyncio.fixture(loop_scope="session")
async def presentation(db, owner_user):
    from app.models import Presentation, PresentationSourceFormat, PresentationStatus

    pres = Presentation(
        owner_id=owner_user.id,
        original_file_name="deck.pdf",
        original_file_url="legacy-compat/deck.pdf",
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
async def presentation_first_session(db, owner_user, presentation):
    from app.models import Session

    session = Session(
        owner_id=owner_user.id,
        unique_code=f"F{uuid.uuid4().hex[:8].upper()}",
        title="Presentation-First Session",
        presentation_id=presentation.id,
        is_live=True,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


@pytest_asyncio.fixture(loop_scope="session")
async def legacy_slide_with_file(db, legacy_ended_session):
    from app.models import Slide

    slide = Slide(
        session_id=legacy_ended_session.id,
        type="CONTENT",
        order=0,
        content_json={"file_url": "legacy-compat/nonexistent.pdf"},
    )
    db.add(slide)
    await db.commit()
    await db.refresh(slide)
    return slide


@pytest_asyncio.fixture(loop_scope="session")
async def legacy_poll_slide_with_responses(db, legacy_live_session):
    """An active POLL slide on a true legacy session, with two responses —
    the data the PDF report's Slide Performance section is built from."""
    from app.models import Response, Slide

    slide = Slide(
        session_id=legacy_live_session.id,
        type="POLL",
        order=0,
        content_json={"question": "Legacy poll question?", "options": ["A", "B"]},
        is_active=True,
    )
    db.add(slide)
    await db.flush()
    db.add_all([
        Response(slide_id=slide.id, value="A", guest_identifier="guest-1"),
        Response(slide_id=slide.id, value="B", guest_identifier="guest-2"),
    ])
    await db.commit()
    await db.refresh(slide)
    return slide


@pytest_asyncio.fixture(loop_scope="session")
async def presentation_first_poll_slide_with_responses(db, presentation_first_session):
    """The presentation-first counterpart: an interaction item is backed by
    an ordinary Slide row (see app/routers/presentations.py module docstring),
    so this looks identical to the legacy fixture above from analytics' point
    of view."""
    from app.models import Response, Slide

    slide = Slide(
        session_id=presentation_first_session.id,
        type="POLL",
        order=0,
        content_json={"question": "Presentation-first poll question?", "options": ["X", "Y"]},
        is_active=True,
    )
    db.add(slide)
    await db.flush()
    db.add_all([
        Response(slide_id=slide.id, value="X", guest_identifier="guest-3"),
    ])
    await db.commit()
    await db.refresh(slide)
    return slide


def _token_for(user):
    from app.auth import create_access_token

    return create_access_token(user.id)


class _FakeRedis:
    """ASGITransport doesn't run app lifespan, so app.state.redis is never
    set. Provides just enough of the redis.asyncio.Redis surface for the
    endpoints under test: publish() (fire-and-forget WS broadcast) and the
    incr/expire pair app/rate_limit.py's check_rate_limit() uses — backed by
    a plain in-memory dict so each test starts with a clean counter."""

    def __init__(self):
        self._counts: dict[str, int] = {}

    async def publish(self, *args, **kwargs):
        pass

    async def incr(self, key):
        self._counts[key] = self._counts.get(key, 0) + 1
        return self._counts[key]

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


class TestLegacySlidePageImageAuthTrueLegacySession:
    """Mirrors test_endpoint_hardening.py::TestLegacySlidePageImageAuth, but
    against a session that never had a presentation attached at all (that
    file's fixtures all set presentation_id)."""

    async def test_no_proof_is_rejected(self, client, legacy_slide_with_file, legacy_ended_session):
        resp = await client.get(
            f"/api/sessions/{legacy_ended_session.id}/slides/{legacy_slide_with_file.id}/page/1"
        )
        assert resp.status_code == 401

    async def test_owner_token_bypasses_liveness(self, client, legacy_slide_with_file, legacy_ended_session, owner_user):
        resp = await client.get(
            f"/api/sessions/{legacy_ended_session.id}/slides/{legacy_slide_with_file.id}/page/1",
            params={"token": _token_for(owner_user)},
        )
        assert resp.status_code != 401

    async def test_other_users_token_is_rejected(self, client, legacy_slide_with_file, legacy_ended_session, other_user):
        resp = await client.get(
            f"/api/sessions/{legacy_ended_session.id}/slides/{legacy_slide_with_file.id}/page/1",
            params={"token": _token_for(other_user)},
        )
        assert resp.status_code == 401


class TestListResponsesLiveGateTrueLegacySession:
    async def test_guest_cannot_list_responses_for_a_non_live_legacy_session(self, client, legacy_slide_with_file):
        resp = await client.get(f"/api/slides/{legacy_slide_with_file.id}/responses/")
        assert resp.status_code == 403

    async def test_owner_can_list_responses_regardless_of_liveness(self, client, legacy_slide_with_file, owner_user):
        resp = await client.get(
            f"/api/slides/{legacy_slide_with_file.id}/responses/",
            headers={"Authorization": f"Bearer {_token_for(owner_user)}"},
        )
        assert resp.status_code == 200

    async def test_guest_can_list_responses_for_a_live_legacy_slide(self, client, legacy_poll_slide_with_responses):
        resp = await client.get(f"/api/slides/{legacy_poll_slide_with_responses.id}/responses/")
        assert resp.status_code == 200
        assert len(resp.json()) == 2


class TestAnalyticsAndPdfDataForBothArchitectures:
    """The PDF report is built entirely from GET /api/analytics/session/{id}/download
    (see frontend/src/routes/dashboard/analytics/[eventId]/[sessionId]/+page.svelte).
    Its 'slides' entries must include content_json (question/options text) for
    BOTH a true legacy session and a presentation-first session — previously
    this metadata came from the legacy-only /slides endpoint, which 409s for
    presentation-first sessions and left the PDF's Slides section blank."""

    async def test_legacy_session_download_includes_slide_content_json(
        self, client, legacy_poll_slide_with_responses, legacy_live_session, owner_user
    ):
        resp = await client.get(
            f"/api/analytics/session/{legacy_live_session.id}/download",
            params={"format": "json"},
            headers={"Authorization": f"Bearer {_token_for(owner_user)}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["slides"]) == 1
        slide = data["slides"][0]
        assert slide["content_json"]["question"] == "Legacy poll question?"
        assert slide["content_json"]["options"] == ["A", "B"]
        assert len(data["responses"]) == 2

    async def test_presentation_first_session_download_includes_slide_content_json(
        self, client, presentation_first_poll_slide_with_responses, presentation_first_session, owner_user
    ):
        resp = await client.get(
            f"/api/analytics/session/{presentation_first_session.id}/download",
            params={"format": "json"},
            headers={"Authorization": f"Bearer {_token_for(owner_user)}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["slides"]) == 1
        slide = data["slides"][0]
        assert slide["content_json"]["question"] == "Presentation-first poll question?"
        assert len(data["responses"]) == 1

    async def test_legacy_session_slides_endpoint_still_works(self, client, legacy_poll_slide_with_responses, legacy_live_session, owner_user):
        """Regression guard: legacy slide CRUD must remain untouched by the
        presentation-first work — see app/routers/slides.py::_ensure_not_presentation_session."""
        resp = await client.get(
            f"/api/sessions/{legacy_live_session.id}/slides/",
            headers={"Authorization": f"Bearer {_token_for(owner_user)}"},
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    async def test_presentation_first_session_rejects_legacy_slides_endpoint(
        self, client, presentation_first_session, owner_user
    ):
        """Unchanged existing behavior: the legacy slide-CRUD endpoint still
        409s for a presentation-first session — analytics/PDF data must come
        from the download endpoint instead, not this one."""
        resp = await client.get(
            f"/api/sessions/{presentation_first_session.id}/slides/",
            headers={"Authorization": f"Bearer {_token_for(owner_user)}"},
        )
        assert resp.status_code == 409


class TestPresentationLibraryEventScopingIdorFix:
    """app/routers/presentations.py::list_my_presentations(event_id=...) —
    verifies a caller can no longer enumerate another user's event by id."""

    async def test_non_owner_cannot_scope_by_someone_elses_event_id(self, client, owner_user, other_user, db):
        from app.models import Event
        from datetime import date

        event = Event(owner_id=owner_user.id, title="Owner's Event", event_date=date.today())
        db.add(event)
        await db.commit()
        await db.refresh(event)

        resp = await client.get(
            "/api/presentations",
            params={"event_id": str(event.id)},
            headers={"Authorization": f"Bearer {_token_for(other_user)}"},
        )
        assert resp.status_code == 404

    async def test_owner_can_scope_by_their_own_event_id(self, client, owner_user, db):
        from app.models import Event
        from datetime import date

        event = Event(owner_id=owner_user.id, title="Owner's Other Event", event_date=date.today())
        db.add(event)
        await db.commit()
        await db.refresh(event)

        resp = await client.get(
            "/api/presentations",
            params={"event_id": str(event.id)},
            headers={"Authorization": f"Bearer {_token_for(owner_user)}"},
        )
        assert resp.status_code == 200

    async def test_malformed_event_id_is_400(self, client, owner_user):
        resp = await client.get(
            "/api/presentations",
            params={"event_id": "not-a-uuid"},
            headers={"Authorization": f"Bearer {_token_for(owner_user)}"},
        )
        assert resp.status_code == 400


class TestExistingAuthUnaffected:
    """Confirms the new per-IP rate limiting in app/routers/auth.py doesn't
    break normal login/register, and correctly rejects once the limit is hit."""

    async def test_register_and_login_still_work(self, client):
        email = f"legacy-auth-{uuid.uuid4().hex[:8]}@example.com"
        reg = await client.post(
            "/api/auth/register",
            json={"email": email, "password": "TestPass123", "invite_code": _invite_code()},
        )
        assert reg.status_code == 201

        login = await client.post(
            "/api/auth/login",
            data={"username": email, "password": "TestPass123"},
        )
        assert login.status_code == 200
        assert "access_token" in login.json()

    async def test_login_is_rate_limited_after_repeated_attempts(self, client):
        from app.routers import auth as auth_router

        for _ in range(auth_router.LOGIN_RATE_LIMIT):
            await client.post(
                "/api/auth/login",
                data={"username": "nobody@example.com", "password": "wrong"},
            )
        resp = await client.post(
            "/api/auth/login",
            data={"username": "nobody@example.com", "password": "wrong"},
        )
        assert resp.status_code == 429


def _invite_code() -> str:
    from app.config import get_settings

    return get_settings().INVITE_CODE
