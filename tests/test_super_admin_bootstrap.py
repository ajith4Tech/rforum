"""
Coverage for the SUPER_ADMIN_EMAIL bootstrap race fix (app/routers/auth.py
::register): auto-promotion now additionally requires a matching
SUPER_ADMIN_BOOTSTRAP_TOKEN and that no SUPER_ADMIN already exists, instead
of trusting a matching email address alone — see app/config.py::
SUPER_ADMIN_BOOTSTRAP_TOKEN for the rationale.

Same dedicated 'rforum_test' Postgres database convention as
test_presentations.py / test_legacy_compatibility.py. The main 'rforum' dev
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
        pytest.skip(
            f"Postgres not reachable at localhost:5433 — skipping super-admin bootstrap tests: {check.stderr.strip()}",
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


class _FakeRedis:
    """ASGITransport doesn't run app lifespan, so app.state.redis is never
    set. Provides just enough of the redis.asyncio.Redis surface for
    register()'s rate limiting (incr/expire)."""

    def __init__(self):
        self._counts: dict[str, int] = {}

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


def _patch_auth_settings(monkeypatch, **overrides):
    """Builds a real Settings object off the actual .env (so INVITE_CODE
    matches what register() checks) with just the super-admin bootstrap
    fields overridden, and patches app.routers.auth's bound get_settings."""
    import app.routers.auth as auth_module
    from app.config import get_settings

    base = get_settings()
    patched = base.model_copy(update=overrides)
    monkeypatch.setattr(auth_module, "get_settings", lambda: patched)
    return patched


async def _register(client, email, invite_code, bootstrap_token=None):
    payload = {"email": email, "password": "TestPass123", "invite_code": invite_code}
    if bootstrap_token is not None:
        payload["super_admin_bootstrap_token"] = bootstrap_token
    return await client.post("/api/auth/register", json=payload)


class TestSuperAdminBootstrap:

    async def test_matching_email_without_bootstrap_token_stays_user(self, client, monkeypatch):
        settings = _patch_auth_settings(
            monkeypatch,
            SUPER_ADMIN_EMAIL="admin@example.com",
            SUPER_ADMIN_BOOTSTRAP_TOKEN="the-real-secret",
        )
        resp = await _register(client, "admin@example.com", settings.INVITE_CODE)
        assert resp.status_code == 201
        assert resp.json()["role"] == "USER"

    async def test_matching_email_with_wrong_bootstrap_token_stays_user(self, client, monkeypatch):
        settings = _patch_auth_settings(
            monkeypatch,
            SUPER_ADMIN_EMAIL="admin2@example.com",
            SUPER_ADMIN_BOOTSTRAP_TOKEN="the-real-secret",
        )
        resp = await _register(
            client, "admin2@example.com", settings.INVITE_CODE, bootstrap_token="wrong-guess"
        )
        assert resp.status_code == 201
        assert resp.json()["role"] == "USER"

    async def test_matching_email_with_correct_bootstrap_token_promotes(self, client, monkeypatch):
        settings = _patch_auth_settings(
            monkeypatch,
            SUPER_ADMIN_EMAIL="admin3@example.com",
            SUPER_ADMIN_BOOTSTRAP_TOKEN="the-real-secret",
        )
        resp = await _register(
            client, "admin3@example.com", settings.INVITE_CODE, bootstrap_token="the-real-secret"
        )
        assert resp.status_code == 201
        assert resp.json()["role"] == "SUPER_ADMIN"

    async def test_bootstrap_is_one_time_only(self, client, monkeypatch):
        """Once a SUPER_ADMIN exists, a second registration with the matching
        email + correct token must NOT also be promoted — closes the race
        where an attacker who doesn't win the first registration could still
        piggyback a later one onto the same bootstrap credentials."""
        settings = _patch_auth_settings(
            monkeypatch,
            SUPER_ADMIN_EMAIL="admin4@example.com",
            SUPER_ADMIN_BOOTSTRAP_TOKEN="the-real-secret",
        )
        first = await _register(
            client, "admin4@example.com", settings.INVITE_CODE, bootstrap_token="the-real-secret"
        )
        assert first.json()["role"] == "SUPER_ADMIN"

        second_email = f"someone-else-{uuid.uuid4().hex[:8]}@example.com"
        second = await _register(
            client, second_email, settings.INVITE_CODE, bootstrap_token="the-real-secret"
        )
        assert second.status_code == 201
        assert second.json()["role"] == "USER"

    async def test_non_admin_email_ignores_bootstrap_token(self, client, monkeypatch):
        settings = _patch_auth_settings(
            monkeypatch,
            SUPER_ADMIN_EMAIL="admin5@example.com",
            SUPER_ADMIN_BOOTSTRAP_TOKEN="the-real-secret",
        )
        resp = await _register(
            client, "not-the-admin@example.com", settings.INVITE_CODE, bootstrap_token="the-real-secret"
        )
        assert resp.status_code == 201
        assert resp.json()["role"] == "USER"
