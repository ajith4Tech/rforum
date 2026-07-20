"""
Integration tests proving the Presentation upload/dedup/lazy-render/delete
lifecycle (already covered against LocalFilesystemBackend in
tests/test_presentations.py) behaves identically when STORAGE_PROVIDER=s3 —
i.e. the storage-backend swap in app/storage/__init__.py is truly transparent
to the router layer. Same DB/ASGI-client pattern as test_presentations.py,
with the storage backend override pointed at a moto-mocked S3 bucket instead
of a tmp_path filesystem.
"""
import io
import os

import boto3
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from moto import mock_aws
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

pytestmark = pytest.mark.asyncio(loop_scope="session")

TEST_DATABASE_URL = "postgresql+asyncpg://rforum:rforum@localhost:5433/rforum_test"
REGION = "eu-north-1"
BUCKET = "rforum-uploads-test"


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
            f"Postgres not reachable at localhost:5433 — skipping integration tests: {check.stderr.strip()}",
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

    user = User(email="s3owner@example.com", hashed_password="x", role="USER")
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture(loop_scope="session")
async def owner_session(db, owner_user):
    from app.models import Session

    session = Session(owner_id=owner_user.id, unique_code="S3TEST-01", title="S3 Test Session")
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


@pytest.fixture
def s3_mock():
    # Function-scoped (not session-scoped): mock_aws() patches botocore
    # process-globally, so it must fully exit after every test — otherwise
    # the bucket it creates here would leak into every later test file that
    # also tries to create a bucket with the same name (BucketAlreadyOwnedByYou).
    with mock_aws():
        boto3.client("s3", region_name=REGION).create_bucket(
            Bucket=BUCKET, CreateBucketConfiguration={"LocationConstraint": REGION},
        )
        yield


@pytest_asyncio.fixture(loop_scope="session")
async def client(db, test_engine, owner_user, s3_mock, tmp_path, monkeypatch):
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

    backend = FallbackStorageBackend(
        primary=S3StorageBackend(bucket=BUCKET, region=REGION, prefix="presentations"),
        secondary=LocalFilesystemBackend(root=str(tmp_path / "uploads")),
    )

    import app.routers.presentations as presentations_module
    monkeypatch.setattr(presentations_module, "get_storage_backend", lambda: backend)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        ac.storage = backend  # test-only escape hatch to inspect S3 state directly
        yield ac

    app.dependency_overrides.clear()


async def _upload(client, session_id, filename, content, content_type="application/pdf"):
    return await client.post(
        f"/api/sessions/{session_id}/presentation/upload",
        files={"file": (filename, io.BytesIO(content), content_type)},
    )


def _token_for(user):
    from app.auth import create_access_token

    return create_access_token(user.id)


class TestUploadAndDownload:

    async def test_upload_stores_original_and_thumbs_in_s3(self, client, owner_session, pdf_3_pages):
        resp = await _upload(client, owner_session.id, "deck.pdf", pdf_3_pages)
        assert resp.status_code == 201
        body = resp.json()
        assert body["reused_existing"] is False
        presentation_id = body["presentation"]["id"]

        keys = client.storage.primary.list_keys("presentations")
        matching = [k for k in keys if presentation_id in k]
        assert any(k.endswith("original/deck.pdf") for k in matching)
        assert any("thumbnails/page_001.webp" in k for k in matching)
        assert any("thumbnails/page_003.webp" in k for k in matching)
        # user-scoped hierarchy: presentations/<sanitized_username>__u_<user_id>/<presentation_id>/...
        assert any(f"__u_{owner_session.owner_id}/{presentation_id}/" in k for k in matching)

    async def test_download_streams_original_from_s3(self, client, owner_session, pdf_1_page):
        resp = await _upload(client, owner_session.id, "deck.pdf", pdf_1_page)
        presentation_id = resp.json()["presentation"]["id"]

        download = await client.get(f"/api/presentations/{presentation_id}/download")
        assert download.status_code == 200
        assert download.content == pdf_1_page


class TestDedup:

    async def test_duplicate_upload_reuses_existing_presentation_without_new_s3_object(
        self, client, owner_session, pdf_1_page
    ):
        first = await _upload(client, owner_session.id, "deck.pdf", pdf_1_page)
        assert first.json()["reused_existing"] is False
        pres_id = first.json()["presentation"]["id"]
        keys_before = set(client.storage.primary.list_keys("presentations"))

        await client.post(f"/api/sessions/{owner_session.id}/presentation/detach")
        second = await _upload(client, owner_session.id, "deck-again.pdf", pdf_1_page)

        assert second.json()["reused_existing"] is True
        assert second.json()["presentation"]["id"] == pres_id
        keys_after = set(client.storage.primary.list_keys("presentations"))
        assert keys_after == keys_before  # no new original/thumb objects written to S3


class TestLazyRendering:

    async def test_first_page_view_renders_and_caches_in_s3(self, client, owner_session, owner_user, pdf_3_pages):
        upload_resp = await _upload(client, owner_session.id, "deck.pdf", pdf_3_pages)
        presentation_id = upload_resp.json()["presentation"]["id"]
        auth = {"token": _token_for(owner_user)}

        keys_before = [k for k in client.storage.primary.list_keys("presentations") if "/pages/" in k]
        assert keys_before == []  # full-res pages not rendered at upload time

        img_resp = await client.get(f"/api/presentations/{presentation_id}/pages/1/image", params=auth)
        assert img_resp.status_code == 200
        # Not "immutable": regenerate_presentation can replace the bytes behind
        # this same URL, so the response is cacheable but bounded, not permanent.
        assert img_resp.headers["cache-control"] == "public, max-age=3600"

        keys_after = [k for k in client.storage.primary.list_keys("presentations") if "/pages/" in k]
        assert len(keys_after) == 1  # rendered and cached in S3 on first view

        img_resp_2 = await client.get(f"/api/presentations/{presentation_id}/pages/1/image", params=auth)
        assert img_resp_2.status_code == 200
        assert img_resp_2.content == img_resp.content  # served from the S3 cache, not re-rendered

    async def test_thumbnail_available_immediately_without_view(self, client, owner_session, owner_user, pdf_1_page):
        upload_resp = await _upload(client, owner_session.id, "deck.pdf", pdf_1_page)
        presentation_id = upload_resp.json()["presentation"]["id"]

        resp = await client.get(
            f"/api/presentations/{presentation_id}/pages/1/thumbnail",
            params={"token": _token_for(owner_user)},
        )
        assert resp.status_code == 200


class TestDelete:

    async def test_delete_removes_all_s3_objects_for_presentation(self, client, owner_session, pdf_1_page):
        upload_resp = await _upload(client, owner_session.id, "deck.pdf", pdf_1_page)
        presentation_id = upload_resp.json()["presentation"]["id"]

        await client.get(f"/api/presentations/{presentation_id}/pages/1/image")  # populate a rendered page too
        await client.post(f"/api/sessions/{owner_session.id}/presentation/detach")

        resp = await client.delete(f"/api/presentations/{presentation_id}")
        assert resp.status_code == 204

        remaining = [
            k for k in client.storage.primary.list_keys("presentations") if presentation_id in k
        ]
        assert remaining == []
