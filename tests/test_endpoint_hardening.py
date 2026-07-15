"""
Integration tests for the public-endpoint hardening pass: the presentation
page/thumbnail IDOR fix, the legacy slide page-image IDOR fix, list_responses'
new live-session gate, clear_responses' SUPER_ADMIN bypass, and analytics'
UUID-parsing fix — against a real (dedicated) 'rforum_test' Postgres database,
same convention as test_presentations.py. The main 'rforum' dev database is
never touched.
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
        pytest.skip(f"Postgres not reachable at localhost:5433 — skipping hardening tests: {check.stderr.strip()}")
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

    user = User(email="hardening-owner@example.com", hashed_password="x", role="USER")
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture(loop_scope="session")
async def other_user(db):
    from app.models import User

    user = User(email="hardening-other@example.com", hashed_password="x", role="USER")
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture(loop_scope="session")
async def admin_user(db):
    from app.models import User

    user = User(email="hardening-admin@example.com", hashed_password="x", role="SUPER_ADMIN")
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture(loop_scope="session")
async def presentation(db, owner_user):
    from app.models import Presentation, PresentationSourceFormat, PresentationStatus

    pres = Presentation(
        owner_id=owner_user.id,
        original_file_name="deck.pdf",
        original_file_url="hardening/deck.pdf",
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
async def live_session_with_presentation(db, owner_user, presentation):
    from app.models import Session

    session = Session(
        owner_id=owner_user.id,
        unique_code=f"L{uuid.uuid4().hex[:8].upper()}",
        title="Live Presentation Session",
        presentation_id=presentation.id,
        is_live=True,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


@pytest_asyncio.fixture(loop_scope="session")
async def ended_session_with_presentation(db, owner_user, presentation):
    from app.models import Session

    session = Session(
        owner_id=owner_user.id,
        unique_code=f"E{uuid.uuid4().hex[:8].upper()}",
        title="Ended Presentation Session",
        presentation_id=presentation.id,
        is_live=False,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


@pytest_asyncio.fixture(loop_scope="session")
async def unrelated_live_session(db, owner_user):
    from app.models import Session

    session = Session(
        owner_id=owner_user.id,
        unique_code=f"U{uuid.uuid4().hex[:8].upper()}",
        title="Unrelated Live Session",
        is_live=True,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


@pytest_asyncio.fixture(loop_scope="session")
async def slide_with_file(db, ended_session_with_presentation):
    from app.models import Slide

    slide = Slide(
        session_id=ended_session_with_presentation.id,
        type="CONTENT",
        order=0,
        content_json={"file_url": "hardening/nonexistent.pdf"},
    )
    db.add(slide)
    await db.commit()
    await db.refresh(slide)
    return slide


@pytest_asyncio.fixture(loop_scope="session")
async def live_slide(db, live_session_with_presentation):
    from app.models import Slide

    slide = Slide(
        session_id=live_session_with_presentation.id,
        type="CONTENT",
        order=0,
        content_json={},
        is_active=True,
    )
    db.add(slide)
    await db.commit()
    await db.refresh(slide)
    return slide


@pytest_asyncio.fixture(loop_scope="session")
async def ended_slide(db, ended_session_with_presentation):
    from app.models import Slide

    slide = Slide(
        session_id=ended_session_with_presentation.id,
        type="CONTENT",
        order=0,
        content_json={},
        is_active=True,
    )
    db.add(slide)
    await db.commit()
    await db.refresh(slide)
    return slide


def _token_for(user):
    from app.auth import create_access_token

    return create_access_token(user.id)


class _FakeRedis:
    """ASGITransport doesn't run app lifespan, so app.state.redis is never set —
    clear_responses() only needs .publish() to fire-and-forget the WS broadcast."""

    async def publish(self, *args, **kwargs):
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


class TestPresentationPageImageAuth:
    async def test_no_proof_is_rejected(self, client, presentation):
        resp = await client.get(f"/api/presentations/{presentation.id}/pages/1/image")
        assert resp.status_code == 401

    async def test_wrong_code_is_rejected(self, client, presentation, unrelated_live_session):
        resp = await client.get(
            f"/api/presentations/{presentation.id}/pages/1/image",
            params={"code": unrelated_live_session.unique_code},
        )
        assert resp.status_code == 401

    async def test_non_live_sessions_code_is_rejected(self, client, presentation, ended_session_with_presentation):
        resp = await client.get(
            f"/api/presentations/{presentation.id}/pages/1/image",
            params={"code": ended_session_with_presentation.unique_code},
        )
        assert resp.status_code == 401

    async def test_matching_live_sessions_code_is_authorized(self, client, presentation, live_session_with_presentation):
        resp = await client.get(
            f"/api/presentations/{presentation.id}/pages/1/image",
            params={"code": live_session_with_presentation.unique_code},
        )
        # Authorization passes; 404 here just means no PresentationPage row/file exists.
        assert resp.status_code != 401

    async def test_owner_token_bypasses_liveness(self, client, presentation, owner_user, ended_session_with_presentation):
        resp = await client.get(
            f"/api/presentations/{presentation.id}/pages/1/image",
            params={"token": _token_for(owner_user)},
        )
        assert resp.status_code != 401

    async def test_other_users_token_is_rejected(self, client, presentation, other_user):
        resp = await client.get(
            f"/api/presentations/{presentation.id}/pages/1/image",
            params={"token": _token_for(other_user)},
        )
        assert resp.status_code == 401

    async def test_malformed_presentation_id_is_400(self, client):
        resp = await client.get("/api/presentations/not-a-uuid/pages/1/image")
        assert resp.status_code == 400


class TestLegacySlidePageImageAuth:
    async def test_no_proof_is_rejected(self, client, slide_with_file, ended_session_with_presentation):
        resp = await client.get(
            f"/api/sessions/{ended_session_with_presentation.id}/slides/{slide_with_file.id}/page/1"
        )
        assert resp.status_code == 401

    async def test_owner_token_bypasses_liveness(self, client, slide_with_file, ended_session_with_presentation, owner_user):
        resp = await client.get(
            f"/api/sessions/{ended_session_with_presentation.id}/slides/{slide_with_file.id}/page/1",
            params={"token": _token_for(owner_user)},
        )
        # Authorization passes; whatever happens next (missing file etc.) is not a 401.
        assert resp.status_code != 401

    async def test_live_sessions_matching_code_is_authorized(self, client, live_slide, live_session_with_presentation):
        resp = await client.get(
            f"/api/sessions/{live_session_with_presentation.id}/slides/{live_slide.id}/page/1",
            params={"code": live_session_with_presentation.unique_code},
        )
        assert resp.status_code != 401


class TestListResponsesLiveGate:
    async def test_guest_cannot_list_responses_for_a_non_live_session(self, client, ended_slide):
        resp = await client.get(f"/api/slides/{ended_slide.id}/responses/")
        assert resp.status_code == 403

    async def test_owner_can_list_responses_regardless_of_liveness(self, client, ended_slide, owner_user):
        resp = await client.get(
            f"/api/slides/{ended_slide.id}/responses/",
            headers={"Authorization": f"Bearer {_token_for(owner_user)}"},
        )
        assert resp.status_code == 200

    async def test_guest_can_list_responses_for_a_live_session(self, client, live_slide):
        resp = await client.get(f"/api/slides/{live_slide.id}/responses/")
        assert resp.status_code == 200


class TestClearResponsesAdminBypass:
    async def test_non_owner_is_still_forbidden(self, client, ended_slide, other_user):
        resp = await client.delete(
            f"/api/slides/{ended_slide.id}/responses/",
            headers={"Authorization": f"Bearer {_token_for(other_user)}"},
        )
        assert resp.status_code == 403

    async def test_super_admin_can_clear_someone_elses_responses(self, client, ended_slide, admin_user):
        resp = await client.delete(
            f"/api/slides/{ended_slide.id}/responses/",
            headers={"Authorization": f"Bearer {_token_for(admin_user)}"},
        )
        assert resp.status_code == 204


class TestAnalyticsUuidValidation:
    async def test_malformed_event_id_is_400_not_500(self, client, owner_user):
        resp = await client.get(
            "/api/analytics/event/not-a-uuid/download",
            headers={"Authorization": f"Bearer {_token_for(owner_user)}"},
        )
        assert resp.status_code == 400

    async def test_malformed_session_id_is_400_not_500(self, client, owner_user):
        resp = await client.get(
            "/api/analytics/session/not-a-uuid/download",
            headers={"Authorization": f"Bearer {_token_for(owner_user)}"},
        )
        assert resp.status_code == 400
