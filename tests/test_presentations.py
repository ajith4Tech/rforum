"""
Integration tests for app/routers/presentations.py against a real (dedicated)
Postgres test database. Mocking every sequential db.execute() call in these
endpoints would be brittle and wouldn't actually validate the lifecycle logic
(dedup, orphan marking, detach/attach reference tracking, FK constraints) —
so these tests exercise the real ORM models through the real endpoints using
an in-process ASGI client, against a separate 'rforum_test' database on the
same Postgres instance the dev stack already runs (see docker-compose.yml).
The main 'rforum' dev database is never touched.

Uses httpx.AsyncClient(transport=ASGITransport(...)) rather than FastAPI's
synchronous TestClient: TestClient runs requests in a background-thread
event loop, which can't share the asyncpg connection created by our
pytest-asyncio DB fixtures — ASGITransport runs everything in the same loop.
"""
import io
import os

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

pytestmark = pytest.mark.asyncio(loop_scope="session")

os.environ.setdefault("STORAGE_BACKEND", "local")

TEST_DATABASE_URL = "postgresql+asyncpg://rforum:rforum@localhost:5433/rforum_test"
ADMIN_DATABASE_URL = "postgresql://rforum:rforum@localhost:5433/rforum"


def _require_test_postgres():
    """
    Plain synchronous psql/createdb calls — deliberately NOT asyncpg/asyncio.
    Running asyncpg through asyncio.run() at module-import time (before any
    pytest-asyncio loop exists) leaves cross-loop state that corrupts later
    asyncpg connections opened inside pytest-asyncio's own event loop.
    """
    import subprocess

    env = {**os.environ, "PGPASSWORD": "rforum"}
    check = subprocess.run(
        ["psql", "-h", "localhost", "-p", "5433", "-U", "rforum", "-d", "rforum", "-tAc",
         "SELECT 1 FROM pg_database WHERE datname = 'rforum_test'"],
        capture_output=True, text=True, env=env,
    )
    if check.returncode != 0:
        pytest.skip(f"Postgres not reachable at localhost:5433 — skipping integration tests: {check.stderr.strip()}")
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
        # Idempotent across repeated local test runs against the same
        # long-lived rforum_test database (drop_all also removes native
        # Postgres enum types, avoiding "type already exists" on a rerun).
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

    # Clean up via a standalone asyncpg connection rather than reusing the
    # SQLAlchemy engine's pool — a pooled connection touched from both this
    # fixture and the concurrently-running ASGI request-handling sessions
    # trips asyncpg's single-operation-in-flight guard even when awaited
    # strictly sequentially, because each is a distinct asyncio Task.
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

    user = User(email="owner@example.com", hashed_password="x", role="USER")
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture(loop_scope="session")
async def other_user(db):
    from app.models import User

    user = User(email="other@example.com", hashed_password="x", role="USER")
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture(loop_scope="session")
async def owner_session(db, owner_user):
    from app.models import Session

    session = Session(owner_id=owner_user.id, unique_code="TEST-0001", title="Test Session")
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


@pytest_asyncio.fixture(loop_scope="session")
async def second_owner_session(db, owner_user):
    from app.models import Session

    session = Session(owner_id=owner_user.id, unique_code="TEST-0002", title="Second Session")
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


@pytest_asyncio.fixture(loop_scope="session")
async def client(db, test_engine, owner_user, tmp_path, monkeypatch):
    from app.auth import get_current_user
    from app.database import get_db
    from app.main import app
    from app.storage.local import LocalFilesystemBackend

    # A fresh Session per request, bound to the same test_engine — mirrors
    # app/database.py::get_db exactly. Sharing the single `db` fixture
    # session (used only for seeding fixture rows) between test setup code
    # and concurrent request handling trips asyncpg's single-operation-in-
    # flight guard, since ASGI request handling can run as its own Task.
    request_session_factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db():
        async with request_session_factory() as session:
            yield session

    def override_get_current_user():
        return owner_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    # presentations.py imported get_storage_backend by name into its own
    # module namespace, so patch that binding directly (patching
    # app.storage.get_storage_backend wouldn't affect the already-bound name).
    import app.routers.presentations as presentations_module
    monkeypatch.setattr(
        presentations_module, "get_storage_backend",
        lambda: LocalFilesystemBackend(root=str(tmp_path / "uploads")),
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


async def _upload(client, session_id, filename, content, content_type="application/pdf"):
    return await client.post(
        f"/api/sessions/{session_id}/presentation/upload",
        files={"file": (filename, io.BytesIO(content), content_type)},
    )


async def _replace(client, session_id, filename, content, content_type="application/pdf"):
    return await client.post(
        f"/api/sessions/{session_id}/presentation/replace",
        files={"file": (filename, io.BytesIO(content), content_type)},
    )


class TestUpload:

    async def test_upload_creates_presentation_with_pages(self, client, owner_session, pdf_3_pages):
        resp = await _upload(client, owner_session.id, "deck.pdf", pdf_3_pages)
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["presentation"]["page_count"] == 3
        assert len(body["timeline"]["items"]) == 3
        assert all(item["item_type"] == "PAGE" for item in body["timeline"]["items"])
        assert body["reused_existing"] is False

    async def test_upload_does_not_eagerly_render_full_pages(self, client, owner_session, pdf_3_pages, tmp_path):
        resp = await _upload(client, owner_session.id, "deck.pdf", pdf_3_pages)
        assert resp.status_code == 201
        presentation_id = resp.json()["presentation"]["id"]

        # Only thumbnails + original should exist on disk — no pages/ files yet.
        pages_dirs = list(tmp_path.glob(f"uploads/presentations/*/{presentation_id}/pages"))
        assert pages_dirs == [] or all(not any(d.iterdir()) for d in pages_dirs)
        thumbs_dirs = list(tmp_path.glob(f"uploads/presentations/*/{presentation_id}/thumbs"))
        assert len(thumbs_dirs) == 1
        assert len(list(thumbs_dirs[0].iterdir())) == 3

    async def test_second_upload_on_same_session_conflicts(self, client, owner_session, pdf_1_page):
        await _upload(client, owner_session.id, "deck.pdf", pdf_1_page)
        resp = await _upload(client, owner_session.id, "deck2.pdf", pdf_1_page)
        assert resp.status_code == 409

    async def test_duplicate_upload_reuses_existing_presentation(
        self, client, owner_session, second_owner_session, pdf_3_pages
    ):
        first = await _upload(client, owner_session.id, "deck.pdf", pdf_3_pages)
        second = await _upload(client, second_owner_session.id, "deck-renamed.pdf", pdf_3_pages)

        assert first.status_code == 201
        assert second.status_code == 201
        assert first.json()["presentation"]["id"] == second.json()["presentation"]["id"]
        assert first.json()["reused_existing"] is False
        assert second.json()["reused_existing"] is True

    async def test_corrupted_upload_returns_422_and_leaves_no_presentation(
        self, client, owner_session, corrupted_pdf_bytes
    ):
        resp = await _upload(client, owner_session.id, "bad.pdf", corrupted_pdf_bytes)
        assert resp.status_code == 422

        library = await client.get("/api/presentations")
        assert library.json() == []


class TestLazyPageRendering:

    async def test_first_page_view_renders_and_caches(self, client, owner_session, pdf_3_pages, tmp_path):
        resp = await _upload(client, owner_session.id, "deck.pdf", pdf_3_pages)
        presentation_id = resp.json()["presentation"]["id"]

        img_resp = await client.get(f"/api/presentations/{presentation_id}/pages/1/image")
        assert img_resp.status_code == 200
        assert img_resp.headers["content-type"] == "image/webp"
        assert "immutable" in img_resp.headers["cache-control"]

        pages_files = list(tmp_path.glob(f"uploads/presentations/*/{presentation_id}/pages/*.webp"))
        assert len(pages_files) == 1

        # Second request is a pure cache hit — same bytes, no new files created.
        img_resp_2 = await client.get(f"/api/presentations/{presentation_id}/pages/1/image")
        assert img_resp_2.status_code == 200
        assert img_resp_2.content == img_resp.content
        pages_files_after = list(tmp_path.glob(f"uploads/presentations/*/{presentation_id}/pages/*.webp"))
        assert len(pages_files_after) == 1

    async def test_thumbnail_available_immediately_without_view(self, client, owner_session, pdf_1_page):
        resp = await _upload(client, owner_session.id, "deck.pdf", pdf_1_page)
        presentation_id = resp.json()["presentation"]["id"]

        thumb_resp = await client.get(f"/api/presentations/{presentation_id}/pages/1/thumbnail")
        assert thumb_resp.status_code == 200
        assert thumb_resp.headers["content-type"] == "image/webp"


class TestReplace:

    async def test_replace_orphans_old_presentation_when_unreferenced(
        self, client, owner_session, pdf_1_page, pdf_3_pages
    ):
        first = await _upload(client, owner_session.id, "deck.pdf", pdf_1_page)
        old_id = first.json()["presentation"]["id"]

        replace = await _replace(client, owner_session.id, "deck-v2.pdf", pdf_3_pages)
        assert replace.status_code == 200, replace.text
        assert replace.json()["reused_existing"] is False

        library = (await client.get("/api/presentations")).json()
        old_entry = next(p for p in library if p["id"] == old_id)
        assert old_entry["orphaned_since"] is not None

    async def test_replace_keeps_old_presentation_if_referenced_elsewhere(
        self, client, owner_session, second_owner_session, pdf_1_page, pdf_3_pages
    ):
        first = await _upload(client, owner_session.id, "deck.pdf", pdf_1_page)
        old_id = first.json()["presentation"]["id"]
        # Attach the SAME presentation to a second session before replacing the first.
        await client.post(f"/api/sessions/{second_owner_session.id}/presentation/attach/{old_id}")

        await _replace(client, owner_session.id, "deck-v2.pdf", pdf_3_pages)

        library = (await client.get("/api/presentations")).json()
        old_entry = next(p for p in library if p["id"] == old_id)
        assert old_entry["orphaned_since"] is None

    async def test_replace_with_identical_bytes_rejected(self, client, owner_session, pdf_1_page):
        await _upload(client, owner_session.id, "deck.pdf", pdf_1_page)
        resp = await _replace(client, owner_session.id, "deck-again.pdf", pdf_1_page)
        assert resp.status_code == 400


class TestDetachAttach:

    async def test_detach_clears_session_pointer_but_keeps_presentation(self, client, owner_session, pdf_1_page):
        upload_resp = await _upload(client, owner_session.id, "deck.pdf", pdf_1_page)
        presentation_id = upload_resp.json()["presentation"]["id"]

        detach_resp = await client.post(f"/api/sessions/{owner_session.id}/presentation/detach")
        assert detach_resp.status_code == 204

        get_resp = await client.get(f"/api/sessions/{owner_session.id}/presentation")
        assert get_resp.status_code == 404  # session no longer has a presentation

        library = (await client.get("/api/presentations")).json()
        assert any(p["id"] == presentation_id for p in library)  # presentation itself still exists

    async def test_detach_marks_orphaned_when_unreferenced(self, client, owner_session, pdf_1_page):
        upload_resp = await _upload(client, owner_session.id, "deck.pdf", pdf_1_page)
        presentation_id = upload_resp.json()["presentation"]["id"]

        await client.post(f"/api/sessions/{owner_session.id}/presentation/detach")

        library = (await client.get("/api/presentations")).json()
        entry = next(p for p in library if p["id"] == presentation_id)
        assert entry["orphaned_since"] is not None

    async def test_attach_reattaches_and_clears_orphaned_mark(
        self, client, owner_session, second_owner_session, pdf_3_pages
    ):
        upload_resp = await _upload(client, owner_session.id, "deck.pdf", pdf_3_pages)
        presentation_id = upload_resp.json()["presentation"]["id"]
        await client.post(f"/api/sessions/{owner_session.id}/presentation/detach")

        attach_resp = await client.post(
            f"/api/sessions/{second_owner_session.id}/presentation/attach/{presentation_id}"
        )
        assert attach_resp.status_code == 200, attach_resp.text
        assert len(attach_resp.json()["timeline"]["items"]) == 3

        library = (await client.get("/api/presentations")).json()
        entry = next(p for p in library if p["id"] == presentation_id)
        assert entry["orphaned_since"] is None
        assert entry["attached_session_id"] == str(second_owner_session.id)

    async def test_attach_to_session_that_already_has_one_conflicts(
        self, client, owner_session, second_owner_session, pdf_1_page
    ):
        upload_resp = await _upload(client, owner_session.id, "deck.pdf", pdf_1_page)
        presentation_id = upload_resp.json()["presentation"]["id"]
        await _upload(client, second_owner_session.id, "other.pdf", pdf_1_page)

        # second_owner_session already has its own presentation (dedup would even
        # reuse the same row, but it's already attached) — attaching another must 409.
        resp = await client.post(
            f"/api/sessions/{second_owner_session.id}/presentation/attach/{presentation_id}"
        )
        assert resp.status_code == 409


class TestDelete:

    async def test_delete_blocked_while_referenced(self, client, owner_session, pdf_1_page):
        upload_resp = await _upload(client, owner_session.id, "deck.pdf", pdf_1_page)
        presentation_id = upload_resp.json()["presentation"]["id"]

        resp = await client.delete(f"/api/presentations/{presentation_id}")
        assert resp.status_code == 409

    async def test_delete_succeeds_once_detached(self, client, owner_session, pdf_1_page, tmp_path):
        upload_resp = await _upload(client, owner_session.id, "deck.pdf", pdf_1_page)
        presentation_id = upload_resp.json()["presentation"]["id"]
        await client.post(f"/api/sessions/{owner_session.id}/presentation/detach")

        resp = await client.delete(f"/api/presentations/{presentation_id}")
        assert resp.status_code == 204

        library = (await client.get("/api/presentations")).json()
        assert library == []

        remaining_files = list(tmp_path.glob(f"uploads/presentations/*/{presentation_id}/**/*"))
        assert remaining_files == []


class TestLargePresentation:

    async def test_hundred_page_upload_only_renders_thumbnails(self, client, owner_session, tmp_path):
        import fitz

        doc = fitz.open()
        for i in range(100):
            page = doc.new_page()
            page.insert_text((72, 72), f"Page {i + 1}")
        big_pdf = doc.tobytes()
        doc.close()

        resp = await _upload(client, owner_session.id, "big.pdf", big_pdf)
        assert resp.status_code == 201
        assert resp.json()["presentation"]["page_count"] == 100

        pres_id = resp.json()["presentation"]["id"]
        pages_dirs = list(tmp_path.glob(f"uploads/presentations/*/{pres_id}/pages"))
        assert pages_dirs == [] or all(not any(d.iterdir()) for d in pages_dirs)


class TestOwnership:

    async def test_other_user_cannot_see_or_upload_to_someone_elses_session(
        self, client, owner_session, other_user
    ):
        from app.auth import get_current_user
        from app.main import app

        app.dependency_overrides[get_current_user] = lambda: other_user
        import fitz
        doc = fitz.open()
        doc.new_page()
        pdf_bytes = doc.tobytes()
        doc.close()

        resp = await _upload(client, owner_session.id, "deck.pdf", pdf_bytes)
        assert resp.status_code == 404


class TestLastUsedAt:

    async def test_last_used_at_set_on_fresh_upload(self, client, owner_session, pdf_1_page):
        resp = await _upload(client, owner_session.id, "deck.pdf", pdf_1_page)
        assert resp.json()["presentation"]["last_used_at"] is not None

    async def test_last_used_at_refreshed_on_dedup_reuse(
        self, client, owner_session, second_owner_session, pdf_1_page
    ):
        first = await _upload(client, owner_session.id, "deck.pdf", pdf_1_page)
        first_last_used = first.json()["presentation"]["last_used_at"]

        second = await _upload(client, second_owner_session.id, "deck-renamed.pdf", pdf_1_page)
        assert second.json()["reused_existing"] is True
        assert second.json()["presentation"]["last_used_at"] is not None
        assert second.json()["presentation"]["last_used_at"] >= first_last_used

    async def test_last_used_at_set_on_attach(self, client, owner_session, second_owner_session, pdf_1_page):
        upload_resp = await _upload(client, owner_session.id, "deck.pdf", pdf_1_page)
        presentation_id = upload_resp.json()["presentation"]["id"]
        await client.post(f"/api/sessions/{owner_session.id}/presentation/detach")

        attach_resp = await client.post(
            f"/api/sessions/{second_owner_session.id}/presentation/attach/{presentation_id}"
        )
        assert attach_resp.json()["presentation"]["last_used_at"] is not None


class TestDetails:

    async def test_details_includes_owner_email_and_exhaustive_attached_sessions(
        self, client, owner_session, second_owner_session, pdf_1_page
    ):
        upload_resp = await _upload(client, owner_session.id, "deck.pdf", pdf_1_page)
        presentation_id = upload_resp.json()["presentation"]["id"]
        await client.post(f"/api/sessions/{second_owner_session.id}/presentation/attach/{presentation_id}")

        details = await client.get(f"/api/presentations/{presentation_id}/details")
        assert details.status_code == 200, details.text
        body = details.json()
        assert body["owner_email"] == "owner@example.com"
        assert body["storage_status"] == "active"
        session_ids = {s["id"] for s in body["attached_sessions"]}
        assert session_ids == {str(owner_session.id), str(second_owner_session.id)}

    async def test_details_storage_status_active_then_detached_after_detach(
        self, client, owner_session, pdf_1_page
    ):
        upload_resp = await _upload(client, owner_session.id, "deck.pdf", pdf_1_page)
        presentation_id = upload_resp.json()["presentation"]["id"]

        active_details = await client.get(f"/api/presentations/{presentation_id}/details")
        assert active_details.json()["storage_status"] == "active"

        await client.post(f"/api/sessions/{owner_session.id}/presentation/detach")

        detached_details = await client.get(f"/api/presentations/{presentation_id}/details")
        assert detached_details.json()["storage_status"] == "detached"
        assert detached_details.json()["attached_sessions"] == []

    async def test_details_404_for_other_users_presentation(
        self, client, owner_session, other_user, pdf_1_page
    ):
        from app.auth import get_current_user
        from app.main import app

        upload_resp = await _upload(client, owner_session.id, "deck.pdf", pdf_1_page)
        presentation_id = upload_resp.json()["presentation"]["id"]

        app.dependency_overrides[get_current_user] = lambda: other_user
        resp = await client.get(f"/api/presentations/{presentation_id}/details")
        assert resp.status_code == 404

    async def test_details_invalid_uuid_returns_400(self, client):
        resp = await client.get("/api/presentations/not-a-uuid/details")
        assert resp.status_code == 400


class TestLibraryScoping:

    async def test_omitting_event_id_reproduces_current_behavior(self, client, owner_session, pdf_1_page):
        await _upload(client, owner_session.id, "deck.pdf", pdf_1_page)
        library = await client.get("/api/presentations")
        assert library.status_code == 200
        assert len(library.json()) == 1
        assert library.json()[0]["storage_status"] == "active"

    async def test_event_scoped_query_includes_same_event_decks_owned_by_others(
        self, client, db, owner_user, other_user, owner_session, pdf_1_page
    ):
        import datetime as dt

        from app.auth import get_current_user
        from app.main import app
        from app.models import Event, Session as SessionModel

        upload_resp = await _upload(client, owner_session.id, "deck.pdf", pdf_1_page)
        presentation_id = upload_resp.json()["presentation"]["id"]

        event = Event(owner_id=other_user.id, title="Shared Event", event_date=dt.date(2026, 8, 1))
        db.add(event)
        await db.commit()
        await db.refresh(event)

        # owner_session isn't part of the event — attach a second, event-scoped
        # session (owned by owner_user, same event as other_user's) so the
        # presentation is reachable via the event, not via direct ownership.
        event_session = SessionModel(
            owner_id=owner_user.id, event_id=event.id, unique_code="TEST-EVT1", title="Event Session"
        )
        db.add(event_session)
        await db.commit()
        await db.refresh(event_session)
        await client.post(f"/api/sessions/{owner_session.id}/presentation/detach")
        await client.post(
            f"/api/sessions/{event_session.id}/presentation/attach/{presentation_id}"
        )

        # other_user doesn't own the presentation, but the event now has a
        # session referencing it — event_id scoping should surface it.
        app.dependency_overrides[get_current_user] = lambda: other_user
        scoped = await client.get(f"/api/presentations?event_id={event.id}")
        assert scoped.status_code == 200
        assert any(p["id"] == presentation_id for p in scoped.json())

        unscoped = await client.get("/api/presentations")
        assert not any(p["id"] == presentation_id for p in unscoped.json())

    async def test_search_and_sort_params(self, client, owner_session, second_owner_session, pdf_1_page, pdf_3_pages):
        await _upload(client, owner_session.id, "alpha.pdf", pdf_1_page)
        await _upload(client, second_owner_session.id, "beta.pdf", pdf_3_pages)

        by_name = await client.get("/api/presentations?sort=name")
        names = [p["original_file_name"] for p in by_name.json()]
        assert names == sorted(names)

        searched = await client.get("/api/presentations?search=alpha")
        assert len(searched.json()) == 1
        assert searched.json()[0]["original_file_name"] == "alpha.pdf"


class TestDownload:

    async def test_download_streams_original_with_content_disposition(
        self, client, owner_session, pdf_1_page
    ):
        upload_resp = await _upload(client, owner_session.id, "deck.pdf", pdf_1_page)
        presentation_id = upload_resp.json()["presentation"]["id"]

        resp = await client.get(f"/api/presentations/{presentation_id}/download")
        assert resp.status_code == 200
        assert 'filename="deck.pdf"' in resp.headers["content-disposition"]
        assert resp.content == pdf_1_page

    async def test_download_404_when_missing_from_disk(self, client, owner_session, pdf_1_page, tmp_path):
        upload_resp = await _upload(client, owner_session.id, "deck.pdf", pdf_1_page)
        presentation_id = upload_resp.json()["presentation"]["id"]

        for f in tmp_path.glob(f"uploads/presentations/*/{presentation_id}/original*"):
            f.unlink()

        resp = await client.get(f"/api/presentations/{presentation_id}/download")
        assert resp.status_code == 404

    async def test_download_404_for_other_users_presentation(
        self, client, owner_session, other_user, pdf_1_page
    ):
        from app.auth import get_current_user
        from app.main import app

        upload_resp = await _upload(client, owner_session.id, "deck.pdf", pdf_1_page)
        presentation_id = upload_resp.json()["presentation"]["id"]

        app.dependency_overrides[get_current_user] = lambda: other_user
        resp = await client.get(f"/api/presentations/{presentation_id}/download")
        assert resp.status_code == 404
