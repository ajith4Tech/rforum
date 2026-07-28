"""
Integration tests for the Organization Settings / Branding admin feature
(app/routers/org_settings.py) — against a real (dedicated) 'rforum_test'
Postgres database, same convention as tests/test_endpoint_hardening.py. The
main 'rforum' dev database is never touched.
"""
import base64
import os

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

pytestmark = pytest.mark.asyncio(loop_scope="session")

os.environ.setdefault("STORAGE_BACKEND", "local")

TEST_DATABASE_URL = "postgresql+asyncpg://rforum:rforum@localhost:5433/rforum_test"

# 1x1 transparent PNG — passes python-magic detection as image/png.
TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUAAscY"
    "42YAAAAASUVORK5CYII="
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
            f"Postgres not reachable at localhost:5433 — skipping org settings tests: {check.stderr.strip()}",
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
    import app.models  # noqa: F401 — populate Base.metadata before create_all
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
        # org_settings is a seeded singleton, not a normal empty-by-default
        # table — every test should see the same fresh default row, mirroring
        # what the Alembic migration seeds in a real deployment.
        await conn.execute(
            "INSERT INTO org_settings (id, display_name) VALUES (1, 'Your Organization')"
        )
    finally:
        await conn.close()


@pytest_asyncio.fixture(loop_scope="session")
async def other_user(db):
    from app.models import User

    user = User(email="org-settings-user@example.com", hashed_password="x", role="USER")
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture(loop_scope="session")
async def admin_user(db):
    from app.models import User

    user = User(email="org-settings-admin@example.com", hashed_password="x", role="SUPER_ADMIN")
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


def _token_for(user):
    from app.auth import create_access_token

    return create_access_token(user.id)


class _FakeRedis:
    async def publish(self, *args, **kwargs):
        pass


@pytest_asyncio.fixture(loop_scope="session")
async def client(db, test_engine, tmp_path, monkeypatch):
    from app.database import get_db
    from app.main import app
    from app.routers import org_settings as org_settings_module
    from app.storage.local import LocalFilesystemBackend

    monkeypatch.setattr(
        org_settings_module, "get_storage_backend",
        lambda: LocalFilesystemBackend(root=str(tmp_path / "uploads")),
    )

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


def _auth(user):
    return {"Authorization": f"Bearer {_token_for(user)}"}


# ── Public read ─────────────────────────────────────────────────────────────

class TestPublicRead:

    async def test_returns_defaults_unauthenticated(self, client):
        resp = await client.get("/api/settings/org")
        assert resp.status_code == 200
        body = resp.json()
        assert body["display_name"] == "Your Organization"
        assert body["logo_url"] == "/api/branding/logo"
        assert body["favicon_url"] == "/api/branding/favicon"
        assert "aws" not in str(body).lower()
        assert "secret" not in str(body).lower()


# ── Display name ────────────────────────────────────────────────────────────

class TestDisplayName:

    async def test_super_admin_can_update(self, client, admin_user):
        resp = await client.patch(
            "/api/admin/settings/org", json={"display_name": "Tech4Good Community"}, headers=_auth(admin_user)
        )
        assert resp.status_code == 200
        assert resp.json()["display_name"] == "Tech4Good Community"

        follow_up = await client.get("/api/settings/org")
        assert follow_up.json()["display_name"] == "Tech4Good Community"

    async def test_normal_user_cannot_update(self, client, other_user):
        resp = await client.patch(
            "/api/admin/settings/org", json={"display_name": "Hijacked Org"}, headers=_auth(other_user)
        )
        assert resp.status_code == 403

    async def test_unauthenticated_cannot_update(self, client):
        resp = await client.patch("/api/admin/settings/org", json={"display_name": "Hijacked Org"})
        assert resp.status_code == 401

    async def test_whitespace_only_name_rejected(self, client, admin_user):
        resp = await client.patch(
            "/api/admin/settings/org", json={"display_name": "   "}, headers=_auth(admin_user)
        )
        assert resp.status_code == 422

    async def test_name_is_trimmed(self, client, admin_user):
        resp = await client.patch(
            "/api/admin/settings/org", json={"display_name": "  Spaced Org  "}, headers=_auth(admin_user)
        )
        assert resp.status_code == 200
        assert resp.json()["display_name"] == "Spaced Org"


# ── Logo ─────────────────────────────────────────────────────────────────────

class TestLogo:

    async def test_super_admin_can_upload(self, client, admin_user):
        resp = await client.put(
            "/api/admin/settings/org/logo",
            files={"file": ("logo.png", TINY_PNG, "image/png")},
            headers=_auth(admin_user),
        )
        assert resp.status_code == 200
        assert resp.json()["has_custom_logo"] is True

    async def test_invalid_extension_rejected(self, client, admin_user):
        resp = await client.put(
            "/api/admin/settings/org/logo",
            files={"file": ("logo.gif", TINY_PNG, "image/gif")},
            headers=_auth(admin_user),
        )
        assert resp.status_code == 400

    async def test_oversized_logo_rejected(self, client, admin_user):
        oversized = b"\x89PNG" + b"0" * (2 * 1024 * 1024 + 100)
        resp = await client.put(
            "/api/admin/settings/org/logo",
            files={"file": ("logo.png", oversized, "image/png")},
            headers=_auth(admin_user),
        )
        assert resp.status_code in (400, 413)

    async def test_super_admin_can_delete(self, client, admin_user):
        await client.put(
            "/api/admin/settings/org/logo",
            files={"file": ("logo.png", TINY_PNG, "image/png")},
            headers=_auth(admin_user),
        )
        resp = await client.delete("/api/admin/settings/org/logo", headers=_auth(admin_user))
        assert resp.status_code == 200
        assert resp.json()["has_custom_logo"] is False

    async def test_normal_user_cannot_upload(self, client, other_user):
        resp = await client.put(
            "/api/admin/settings/org/logo",
            files={"file": ("logo.png", TINY_PNG, "image/png")},
            headers=_auth(other_user),
        )
        assert resp.status_code == 403

    async def test_default_returned_when_no_custom_logo(self, client):
        resp = await client.get("/api/branding/logo", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "/logo-mascot.webp"

    async def test_custom_logo_served_after_upload(self, client, admin_user):
        await client.put(
            "/api/admin/settings/org/logo",
            files={"file": ("logo.png", TINY_PNG, "image/png")},
            headers=_auth(admin_user),
        )
        resp = await client.get("/api/branding/logo", follow_redirects=False)
        assert resp.status_code == 200
        assert resp.content == TINY_PNG
        assert resp.headers["content-type"] == "image/png"


# ── Favicon ──────────────────────────────────────────────────────────────────

class TestFavicon:

    async def test_super_admin_can_upload(self, client, admin_user):
        resp = await client.put(
            "/api/admin/settings/org/favicon",
            files={"file": ("favicon.png", TINY_PNG, "image/png")},
            headers=_auth(admin_user),
        )
        assert resp.status_code == 200
        assert resp.json()["has_custom_favicon"] is True

    async def test_invalid_extension_rejected(self, client, admin_user):
        resp = await client.put(
            "/api/admin/settings/org/favicon",
            files={"file": ("favicon.jpg", TINY_PNG, "image/jpeg")},
            headers=_auth(admin_user),
        )
        assert resp.status_code == 400

    async def test_oversized_favicon_rejected(self, client, admin_user):
        oversized = b"\x89PNG" + b"0" * (256 * 1024 + 100)
        resp = await client.put(
            "/api/admin/settings/org/favicon",
            files={"file": ("favicon.png", oversized, "image/png")},
            headers=_auth(admin_user),
        )
        assert resp.status_code in (400, 413)

    async def test_super_admin_can_delete(self, client, admin_user):
        await client.put(
            "/api/admin/settings/org/favicon",
            files={"file": ("favicon.png", TINY_PNG, "image/png")},
            headers=_auth(admin_user),
        )
        resp = await client.delete("/api/admin/settings/org/favicon", headers=_auth(admin_user))
        assert resp.status_code == 200
        assert resp.json()["has_custom_favicon"] is False

    async def test_default_returned_when_no_custom_favicon(self, client):
        resp = await client.get("/api/branding/favicon", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "/favicon.ico"


# ── Storage keys / org prefix ────────────────────────────────────────────────

class TestStorageKeyShape:

    async def test_branding_key_builders_produce_expected_shape(self):
        from app.storage.keys import branding_favicon_key, branding_logo_key

        assert branding_logo_key(".png") == "branding/logo.png"
        assert branding_favicon_key(".ico") == "branding/favicon.ico"

    async def test_branding_keys_respect_s3_org_prefix(self):
        """S3_PREFIX (app/config.py) doubles as the per-organization namespace
        segment in the one-instance-per-org deployment model — verifies a
        branding key ends up under that prefix in the bucket, exactly like
        every Presentation key already does (see app/storage/s3.py)."""
        import boto3
        from moto import mock_aws

        from app.storage.keys import branding_logo_key
        from app.storage.s3 import S3StorageBackend

        bucket = "rforum-uploads-test-org-prefix"
        region = "eu-north-1"
        with mock_aws():
            boto3.client("s3", region_name=region).create_bucket(
                Bucket=bucket, CreateBucketConfiguration={"LocationConstraint": region},
            )
            backend = S3StorageBackend(bucket=bucket, region=region, prefix="rforum/org-a")
            key = branding_logo_key(".png")
            backend.save(key, TINY_PNG)

            raw = boto3.client("s3", region_name=region).get_object(
                Bucket=bucket, Key="rforum/org-a/branding/logo.png"
            )
            assert raw["Body"].read() == TINY_PNG


# ── Singleton enforcement ────────────────────────────────────────────────────

class TestSingleton:

    async def test_cannot_create_a_second_row(self, db):
        from sqlalchemy.exc import IntegrityError

        from app.models import OrgSettings

        db.add(OrgSettings(id=2, display_name="Second Org"))
        with pytest.raises(IntegrityError):
            await db.commit()
