"""Tests for scripts/migrate_presentations_to_s3.py — DB-driven backfill of
local presentation assets into S3. Verifies dry-run, skip-existing (checksum
verified via ETag), reupload-on-mismatch, resumability (idempotent re-run),
missing-asset reporting, and the preflight bucket-access check.

Uses a real (dedicated) Postgres test database — same 'rforum_test' database
and fixture conventions as tests/test_presentations.py — since the script's
whole point is to read Presentation/PresentationPage rows, not local files.
"""
import importlib.util
import os
import sys
import uuid
from pathlib import Path

import boto3
import pytest
import pytest_asyncio
from moto import mock_aws
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

pytestmark = pytest.mark.asyncio(loop_scope="session")

SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "migrate_presentations_to_s3.py"
TEST_DATABASE_URL = "postgresql+asyncpg://rforum:rforum@localhost:5433/rforum_test"

REGION = "eu-north-1"
BUCKET = "rforum-uploads-test"


def _load_script_module():
    spec = importlib.util.spec_from_file_location("migrate_presentations_to_s3", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


migrate = _load_script_module()


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


class _Args:
    def __init__(self, dry_run=False, limit=None, verbose=False):
        self.dry_run = dry_run
        self.limit = limit
        self.verbose = verbose


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

    session_factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    import asyncpg

    conn = await asyncpg.connect(TEST_DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://"))
    try:
        table_names = ", ".join(t.name for t in Base.metadata.sorted_tables)
        await conn.execute(f"TRUNCATE TABLE {table_names} CASCADE")
    finally:
        await conn.close()


@pytest.fixture
def local_root(tmp_path):
    return tmp_path / "uploads"


@pytest.fixture
def s3_bucket():
    with mock_aws():
        boto3.client("s3", region_name=REGION).create_bucket(
            Bucket=BUCKET, CreateBucketConfiguration={"LocationConstraint": REGION},
        )
        yield


@pytest.fixture(autouse=True)
def _patch_settings(monkeypatch, local_root, s3_bucket):
    from app.config import Settings

    settings = Settings(
        STORAGE_ROOT=str(local_root),
        S3_BUCKET=BUCKET,
        S3_REGION=REGION,
        S3_PREFIX="",
    )
    monkeypatch.setattr("app.config.get_settings", lambda: settings)


@pytest_asyncio.fixture(autouse=True)
async def _patch_db_session(monkeypatch, test_engine):
    # The script imports `async_session` from app.database inside _run() —
    # point it at the test engine so it reads/writes rforum_test, never the
    # real dev database.
    session_factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr("app.database.async_session", session_factory)


async def _make_presentation(db, *, with_pdf_cache=False, with_page_image=True, with_thumbnail=True,
                              n_pages=1, filename="deck.pdf"):
    """Seed one User + Presentation + PresentationPage(s), writing whichever
    local asset files are requested via the same key builders/backend the
    app itself uses, so the keys the script derives from the DB rows match
    exactly what's on disk."""
    from app.models import Presentation, PresentationPage, PresentationSourceFormat, PresentationStatus, User
    from app.storage.keys import dir_prefix_from_known_key, original_key, page_key, pdf_key_for_dir, thumbnail_key
    from app.storage.local import LocalFilesystemBackend

    settings = __import__("app.config", fromlist=["get_settings"]).get_settings()
    local_backend = LocalFilesystemBackend(root=settings.STORAGE_ROOT)

    user = User(email=f"user{uuid.uuid4().hex[:8]}@example.com", hashed_password="x", role="USER")
    db.add(user)
    await db.flush()

    presentation_id = uuid.uuid4()
    orig_key = original_key(user.email, user.id, presentation_id, filename)
    local_backend.save(orig_key, b"original bytes")

    pres_dir = dir_prefix_from_known_key(orig_key, presentation_id)
    if with_pdf_cache:
        local_backend.save(pdf_key_for_dir(pres_dir), b"pdf cache bytes")

    presentation = Presentation(
        id=presentation_id,
        owner_id=user.id,
        original_file_name=filename,
        original_file_url=orig_key,
        original_file_type="application/pdf",
        original_file_size=len(b"original bytes"),
        source_format=PresentationSourceFormat.PDF,
        status=PresentationStatus.READY,
        page_count=n_pages,
    )
    db.add(presentation)

    for page_number in range(1, n_pages + 1):
        thumb_key = thumbnail_key(user.email, user.id, presentation_id, page_number)
        img_key = page_key(user.email, user.id, presentation_id, page_number)
        if with_thumbnail:
            local_backend.save(thumb_key, f"thumb {page_number} bytes".encode())
        if with_page_image:
            local_backend.save(img_key, f"page {page_number} bytes".encode())
        db.add(PresentationPage(
            presentation_id=presentation_id, page_number=page_number,
            image_url=img_key, thumbnail_url=thumb_key,
        ))

    await db.commit()
    return presentation


class TestDryRun:

    async def test_dry_run_uploads_nothing(self, db):
        await _make_presentation(db)

        stats = await migrate._run(_Args(dry_run=True))
        assert stats.presentations_total == 1
        assert stats.presentations_migrated == 1
        assert stats.files_uploaded == 3  # original + thumbnail + page image (no pdf cache)

        client = boto3.client("s3", region_name=REGION)
        listing = client.list_objects_v2(Bucket=BUCKET, Prefix="presentations")
        assert listing.get("KeyCount", 0) == 0


class TestUploadAndSkip:

    async def test_first_run_uploads_all_present_assets(self, db):
        presentation = await _make_presentation(db, with_pdf_cache=True)

        stats = await migrate._run(_Args())
        assert stats.presentations_total == 1
        assert stats.presentations_migrated == 1
        assert stats.presentations_failed == 0
        # original + pdf cache + thumbnail + page image = 4
        assert stats.files_uploaded == 4

        client = boto3.client("s3", region_name=REGION)
        obj = client.get_object(Bucket=BUCKET, Key=presentation.original_file_url)
        assert obj["Body"].read() == b"original bytes"

    async def test_second_run_skips_everything_already_verified(self, db):
        await _make_presentation(db, with_pdf_cache=True)

        await migrate._run(_Args())
        stats = await migrate._run(_Args())

        assert stats.files_uploaded == 0
        assert stats.files_skipped_verified == 4
        assert stats.presentations_skipped == 1
        assert stats.presentations_migrated == 0

    async def test_limit_stops_after_n_presentations(self, db):
        await _make_presentation(db)
        await _make_presentation(db)

        stats = await migrate._run(_Args(limit=1))
        assert stats.presentations_total == 1


class TestChecksumMismatch:

    async def test_reuploads_when_remote_object_is_stale(self, db):
        presentation = await _make_presentation(db)
        await migrate._run(_Args())

        client = boto3.client("s3", region_name=REGION)
        client.put_object(Bucket=BUCKET, Key=presentation.original_file_url, Body=b"stale wrong bytes")

        stats = await migrate._run(_Args())
        assert stats.files_reuploaded_mismatch == 1

        obj = client.get_object(Bucket=BUCKET, Key=presentation.original_file_url)
        assert obj["Body"].read() == b"original bytes"


class TestMissingLocalAssets:

    async def test_missing_lazy_page_image_is_routine_not_a_failure(self, db):
        await _make_presentation(db, with_page_image=False)

        stats = await migrate._run(_Args())
        assert stats.presentations_failed == 0
        # original + thumbnail uploaded; pdf cache + page image absent (both routine)
        assert stats.files_uploaded == 2
        categories = {c for (_pid, c, _key) in stats.missing_local_assets}
        assert "page" in categories
        assert "pdf" in categories

    async def test_missing_thumbnail_is_flagged_but_not_fatal(self, db):
        await _make_presentation(db, with_thumbnail=False)

        stats = await migrate._run(_Args())
        # A missing thumbnail is a real data problem, but doesn't block
        # uploading the assets that *are* present (original here).
        assert stats.presentations_failed == 0
        assert any(c == "thumbnail" for (_pid, c, _key) in stats.missing_local_assets)

    async def test_multiple_pages_migrate_independently(self, db):
        await _make_presentation(db, n_pages=3, with_page_image=False)

        stats = await migrate._run(_Args())
        # 1 original + 3 thumbnails uploaded; 3 page images + 1 pdf cache missing (routine)
        assert stats.files_uploaded == 4
        assert len(stats.missing_local_assets) == 4


class TestPreflight:

    async def test_run_raises_clear_error_when_bucket_does_not_exist(self, db, monkeypatch):
        from app.config import Settings

        bad_settings = Settings(
            STORAGE_ROOT=str(Path(__file__).parent), S3_BUCKET="this-bucket-does-not-exist-at-all",
            S3_REGION=REGION, S3_PREFIX="",
        )
        monkeypatch.setattr("app.config.get_settings", lambda: bad_settings)

        with pytest.raises(RuntimeError, match="S3 preflight check failed"):
            await migrate._run(_Args(dry_run=True))
