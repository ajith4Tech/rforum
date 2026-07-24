"""
Targeted coverage for the presentation page-image fan-out fix:

  GET /api/presentations/{presentation_id}/pages/{page_number}/image

Root cause this covers (see app/storage/__init__.py::STORAGE_IO_CONCURRENCY
and app/routers/presentations.py::_serve_page_file): every blocking storage
call in this endpoint used to go through asyncio.to_thread()'s shared
default executor — just min(32, cpu_count()+4) threads (6 on a 2-vCPU host).
Under a real workshop's ~500 concurrent guests requesting the same page,
that queues hundreds of reads behind 6 worker threads, producing multi-
second tail latency and, past that, client-side timeouts/resets plus a
share of genuine 5xx from retry-exhaustion under the extra load. Fixed by:
  1. Routing storage I/O through a dedicated, workshop-sized thread pool
     (STORAGE_IO_EXECUTOR) instead of the shared default one.
  2. Matching the S3 client's max_pool_connections to the same figure, so
     the fix doesn't just relocate the same class of bottleneck.
  3. Catching FileNotFoundError/PermissionError/ConnectionError around the
     previously-unguarded _load_render_source call (404/503 instead of an
     unhandled exception surfacing as a raw 500), and degrading gracefully
     if only the post-render cache-save fails (serve the already-rendered
     bytes rather than fail a request over a cache-write hiccup).

Same dedicated 'rforum_test' Postgres database convention as
test_presentations.py / test_presentations_s3_backend.py. The main 'rforum'
dev database is never touched.
"""
import asyncio
import io
import os

import boto3
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from moto import mock_aws
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

pytestmark = pytest.mark.asyncio(loop_scope="session")

os.environ.setdefault("STORAGE_BACKEND", "local")

TEST_DATABASE_URL = "postgresql+asyncpg://rforum:rforum@localhost:5433/rforum_test"
BUCKET = "rforum-image-concurrency-test"
REGION = "us-east-1"


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
            f"Postgres not reachable at localhost:5433 — skipping image concurrency tests: "
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

    user = User(email="image-concurrency-owner@example.com", hashed_password="x", role="USER")
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture(loop_scope="session")
async def owner_session(db, owner_user):
    from app.models import Session

    session = Session(owner_id=owner_user.id, unique_code="IMGC-0001", title="Image Concurrency Test", is_live=True)
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


@pytest_asyncio.fixture(loop_scope="session")
async def unrelated_session(db, owner_user):
    from app.models import Session

    session = Session(owner_id=owner_user.id, unique_code="IMGC-9999", title="Unrelated Session", is_live=True)
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


def _token_for(user):
    from app.auth import create_access_token

    return create_access_token(user.id)


class _FakeRedis:
    """Deterministic incr/expire/publish stand-in — set explicitly on
    app.state.redis by every client fixture below rather than relying on
    some other test file to have already triggered ASGI lifespan startup
    (or left its own fixture's redis assignment sitting on the shared `app`
    singleton) first — the presentation write-rate-limit check
    (app/routers/presentations.py::_check_presentation_write_rate_limit)
    needs SOMETHING at app.state.redis to exist before upload() can be
    called at all, and ASGITransport never runs lifespan on its own."""

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


async def _upload(client, session_id, filename, content, content_type="application/pdf"):
    return await client.post(
        f"/api/sessions/{session_id}/presentation/upload",
        files={"file": (filename, io.BytesIO(content), content_type)},
    )


# ── Local-backend client: pure concurrency/correctness, no network involved ─

@pytest_asyncio.fixture(loop_scope="session")
async def client(db, test_engine, owner_user, tmp_path, monkeypatch):
    from app.auth import get_current_user
    from app.database import get_db
    from app.main import app
    from app.storage.local import LocalFilesystemBackend

    request_session_factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db():
        async with request_session_factory() as session:
            yield session

    def override_get_current_user():
        return owner_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    app.state.redis = _FakeRedis()

    import app.routers.presentations as presentations_module
    monkeypatch.setattr(
        presentations_module, "get_storage_backend",
        lambda: LocalFilesystemBackend(root=str(tmp_path / "uploads")),
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


# ── S3+Fallback client: for storage-failure-handling tests ──────────────────

@pytest.fixture
def s3_mock():
    # Function-scoped: mock_aws() patches botocore process-globally, so it
    # must fully exit after every test (same reasoning as
    # test_presentations_s3_backend.py::s3_mock).
    with mock_aws():
        boto3.client("s3", region_name=REGION).create_bucket(Bucket=BUCKET)
        yield


@pytest_asyncio.fixture(loop_scope="session")
async def s3_client(db, test_engine, owner_user, s3_mock, tmp_path, monkeypatch):
    from app.auth import get_current_user
    from app.database import get_db
    from app.main import app
    from app.storage.fallback import FallbackStorageBackend
    from app.storage.local import LocalFilesystemBackend
    from app.storage.s3 import S3StorageBackend

    request_session_factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db():
        async with request_session_factory() as session:
            yield session

    def override_get_current_user():
        return owner_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    app.state.redis = _FakeRedis()

    backend = FallbackStorageBackend(
        primary=S3StorageBackend(bucket=BUCKET, region=REGION, prefix="presentations"),
        secondary=LocalFilesystemBackend(root=str(tmp_path / "uploads")),
    )

    import app.routers.presentations as presentations_module
    monkeypatch.setattr(presentations_module, "get_storage_backend", lambda: backend)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        ac.storage = backend  # test-only escape hatch
        yield ac

    app.dependency_overrides.clear()


def _image_url(presentation_id, page=1, **params):
    from urllib.parse import urlencode

    qs = urlencode(params)
    return f"/api/presentations/{presentation_id}/pages/{page}/image" + (f"?{qs}" if qs else "")


# ── 1 / 10 / 100 / 500 concurrent requests ───────────────────────────────────

class TestConcurrencyScales:
    """Same (presentation, page) requested by 1, 10, 100, and 500 concurrent
    'guests' — all must succeed with identical, correct image bytes. This is
    the exact shape of the load-test failure (500 guests, one already-active
    page) that exposed the default-executor bottleneck."""

    @pytest.mark.parametrize("n", [1, 10, 100, 500])
    async def test_n_concurrent_requests_for_the_same_page_all_succeed(
        self, client, owner_session, owner_user, pdf_3_pages, n
    ):
        resp = await _upload(client, owner_session.id, "deck.pdf", pdf_3_pages)
        assert resp.status_code == 201
        presentation_id = resp.json()["presentation"]["id"]
        auth = {"token": _token_for(owner_user)}

        responses = await asyncio.gather(*[
            client.get(_image_url(presentation_id, 1, **auth)) for _ in range(n)
        ])

        statuses = [r.status_code for r in responses]
        assert all(s == 200 for s in statuses), f"n={n}: unexpected statuses {sorted(set(statuses))}"
        # render_page (app/services/file_processing.py) emits webp when
        # available, png otherwise — _serve_page_file picks the media_type
        # from the actual storage key's extension either way.
        assert all(r.headers["content-type"] in ("image/webp", "image/png") for r in responses)
        # Every guest must see the SAME bytes — no partial/corrupt reads
        # under contention, and no two different renders of the same page.
        assert len({r.content for r in responses}) == 1
        assert len(responses[0].content) > 0


class TestConcurrentCacheMiss:
    async def test_concurrent_requests_for_an_uncached_page_render_exactly_once(
        self, client, owner_session, owner_user, pdf_3_pages, monkeypatch
    ):
        """500 guests hitting a page the instant it's activated (never
        rendered before) must still coalesce onto ONE render — the lock in
        _serve_page_file, unaffected by the executor swap. Regression
        coverage at the full 500-guest scale (existing coverage in
        test_presentations.py only exercises 10)."""
        import app.routers.presentations as presentations_module

        resp = await _upload(client, owner_session.id, "deck.pdf", pdf_3_pages)
        presentation_id = resp.json()["presentation"]["id"]
        auth = {"token": _token_for(owner_user)}

        real_render_page = presentations_module.render_page
        call_count = {"n": 0}

        def counting_render_page(*args, **kwargs):
            call_count["n"] += 1
            import time
            time.sleep(0.05)  # widen the race window
            return real_render_page(*args, **kwargs)

        monkeypatch.setattr(presentations_module, "render_page", counting_render_page)

        responses = await asyncio.gather(*[
            client.get(_image_url(presentation_id, 2, **auth)) for _ in range(500)
        ])

        assert all(r.status_code == 200 for r in responses)
        assert len({r.content for r in responses}) == 1
        assert call_count["n"] == 1


# ── Correctness: missing object, auth/session-code ───────────────────────────

class TestMissingImage:
    async def test_nonexistent_page_number_is_404(self, client, owner_session, owner_user, pdf_3_pages):
        resp = await _upload(client, owner_session.id, "deck.pdf", pdf_3_pages)
        presentation_id = resp.json()["presentation"]["id"]
        auth = {"token": _token_for(owner_user)}

        resp = await client.get(_image_url(presentation_id, 99, **auth))
        assert resp.status_code == 404

    async def test_nonexistent_presentation_id_is_401_not_a_leak(self, client, owner_user):
        """_authorize_presentation_asset (app/routers/presentations.py)
        checks authorization BEFORE existence, deliberately: a token that
        can't be matched to an owned, existing presentation is rejected
        with the same 401 a real-but-not-yours presentation would get,
        rather than a 404 that would let a caller distinguish "exists but
        not yours" from "doesn't exist" by status code alone."""
        import uuid

        resp = await client.get(_image_url(str(uuid.uuid4()), 1, token=_token_for(owner_user)))
        assert resp.status_code == 401

    async def test_malformed_presentation_id_is_400(self, client, owner_user):
        resp = await client.get(f"/api/presentations/not-a-uuid/pages/1/image?token={_token_for(owner_user)}")
        assert resp.status_code == 400


class TestAuthorization:
    """Session-code/token gating unchanged by this fix — see
    app/routers/presentations.py::_authorize_presentation_asset. Thin
    supplementary coverage; the exhaustive version lives in
    test_endpoint_hardening.py::TestPresentationPageImageAuth."""

    async def test_no_token_and_no_code_is_401(self, client, owner_session, owner_user, pdf_3_pages):
        resp = await _upload(client, owner_session.id, "deck.pdf", pdf_3_pages)
        presentation_id = resp.json()["presentation"]["id"]

        resp = await client.get(_image_url(presentation_id, 1))
        assert resp.status_code == 401

    async def test_correct_session_code_is_authorized(self, client, owner_session, owner_user, pdf_3_pages):
        resp = await _upload(client, owner_session.id, "deck.pdf", pdf_3_pages)
        presentation_id = resp.json()["presentation"]["id"]

        resp = await client.get(_image_url(presentation_id, 1, code=owner_session.unique_code))
        assert resp.status_code == 200

    async def test_a_different_sessions_code_is_rejected(
        self, client, owner_session, unrelated_session, owner_user, pdf_3_pages
    ):
        resp = await _upload(client, owner_session.id, "deck.pdf", pdf_3_pages)
        presentation_id = resp.json()["presentation"]["id"]

        resp = await client.get(_image_url(presentation_id, 1, code=unrelated_session.unique_code))
        assert resp.status_code == 401


# ── Storage failure handling (the exact gap this fix closes) ────────────────

class TestStorageFailureHandling:
    """Regression coverage for the previously-unguarded _load_render_source
    call in _serve_page_file: a storage error while loading the ORIGINAL
    file to render a not-yet-cached page used to surface as a raw,
    unhandled 500. Now: FileNotFoundError -> 404, PermissionError/
    ConnectionError -> 503 — both real HTTP responses instead of a crash.

    Patches S3StorageBackend.read/save directly (via the FallbackStorageBackend
    the s3_client fixture builds — same composition get_storage_backend()
    uses in production) rather than moto's network layer: it's the exact
    exception types the app's storage contract already defines
    (FileNotFoundError/PermissionError/ConnectionError — see
    app/storage/base.py), and deterministic regardless of moto's own
    fault-injection support for a given S3 operation.
    """

    async def test_missing_original_file_on_cache_miss_is_404_not_500(
        self, s3_client, owner_session, owner_user, pdf_3_pages
    ):
        from unittest.mock import patch

        resp = await _upload(s3_client, owner_session.id, "deck.pdf", pdf_3_pages)
        presentation_id = resp.json()["presentation"]["id"]

        # Every storage read misses — both the cached-page check and, once
        # that falls through to the render path, the original-file read
        # inside _load_render_source. storage.exists() is untouched, so the
        # original-file-exists precondition still passes and execution
        # reaches _load_render_source's own read, which is what this exercises.
        with patch.object(s3_client.storage.primary, "read", side_effect=FileNotFoundError("gone")):
            resp = await s3_client.get(_image_url(presentation_id, 1, token=_token_for(owner_user)))

        assert resp.status_code == 404

    async def test_s3_connection_error_on_cache_miss_is_503_not_500(
        self, s3_client, owner_session, owner_user, pdf_3_pages
    ):
        """FallbackStorageBackend (what get_storage_backend() actually
        returns in production) deliberately normalizes a primary
        ConnectionError into a secondary FileNotFoundError when the
        secondary doesn't have a copy either (app/storage/fallback.py) — so
        this specific 503 branch is only reachable when the configured
        backend IS bare S3StorageBackend, with no local fallback to catch
        the miss. Swaps to that directly for this one request (upload still
        goes through the normal Fallback-wrapped backend) to exercise it."""
        from unittest.mock import patch

        resp = await _upload(s3_client, owner_session.id, "deck.pdf", pdf_3_pages)
        presentation_id = resp.json()["presentation"]["id"]

        bare_s3 = s3_client.storage.primary
        import app.routers.presentations as presentations_module

        # The cached-page read (line ~531) must still miss with
        # FileNotFoundError to reach the render path at all; only the
        # ORIGINAL file read inside _load_render_source should hit the
        # simulated outage — a blanket ConnectionError on every read would
        # raise from the very first, unrelated call instead.
        def flaky_read(key):
            if key.endswith("/original/deck.pdf") or "/original/" in key:
                raise ConnectionError("simulated S3 outage")
            raise FileNotFoundError("not cached yet")

        with patch.object(presentations_module, "get_storage_backend", lambda: bare_s3), \
                patch.object(bare_s3, "read", side_effect=flaky_read):
            resp = await s3_client.get(_image_url(presentation_id, 1, token=_token_for(owner_user)))

        assert resp.status_code == 503

    async def test_cache_save_failure_still_serves_the_rendered_image(
        self, s3_client, owner_session, owner_user, pdf_3_pages
    ):
        """The page was successfully rendered from the original — a
        transient failure writing it back to the cache must not fail the
        request; the bytes are already in hand."""
        from unittest.mock import patch

        resp = await _upload(s3_client, owner_session.id, "deck.pdf", pdf_3_pages)
        presentation_id = resp.json()["presentation"]["id"]

        with patch.object(s3_client.storage.primary, "save", side_effect=ConnectionError("simulated S3 outage")):
            resp = await s3_client.get(_image_url(presentation_id, 1, token=_token_for(owner_user)))

        assert resp.status_code == 200
        assert len(resp.content) > 0


# ── No resource leak under repeated concurrent bursts ────────────────────────

class TestNoResourceLeak:
    async def test_repeated_bursts_do_not_grow_the_storage_executor_or_lock_table_unbounded(
        self, client, owner_session, owner_user, pdf_3_pages
    ):
        from app.storage import STORAGE_IO_CONCURRENCY, STORAGE_IO_EXECUTOR
        import app.routers.presentations as presentations_module

        resp = await _upload(client, owner_session.id, "deck.pdf", pdf_3_pages)
        presentation_id = resp.json()["presentation"]["id"]
        auth = {"token": _token_for(owner_user)}

        locks_before = len(presentations_module._page_render_locks)

        for _ in range(5):  # 5 rounds x 100 concurrent = 500 total requests
            responses = await asyncio.gather(*[
                client.get(_image_url(presentation_id, 1, **auth)) for _ in range(100)
            ])
            assert all(r.status_code == 200 for r in responses)

        # The executor never grows past its fixed configured size, no matter
        # how many bursts it services.
        assert STORAGE_IO_EXECUTOR._max_workers == STORAGE_IO_CONCURRENCY
        assert len(STORAGE_IO_EXECUTOR._threads) <= STORAGE_IO_CONCURRENCY

        # Hitting the SAME (presentation, page) 500 more times must not add
        # more than one lock entry — the lock table is keyed per distinct
        # page, not per request (app/routers/presentations.py's own
        # documented invariant).
        assert len(presentations_module._page_render_locks) == locks_before + 1
