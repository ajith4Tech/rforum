"""Unit tests for app/rate_limit.py's shared fixed-window counter — no
Postgres or real Redis needed, just the incr/expire surface it depends on."""
import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from app.rate_limit import check_rate_limit

pytestmark = pytest.mark.asyncio


class _FakeRedis:
    def __init__(self):
        self.counts: dict[str, int] = {}
        self.expired_keys: list[str] = []

    async def incr(self, key):
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    async def expire(self, key, seconds):
        self.expired_keys.append(key)


class _FailingRedis:
    """Simulates a Redis blip: every call raises a redis-py error."""

    async def incr(self, key):
        raise RedisConnectionError("simulated Redis outage")

    async def expire(self, key, seconds):
        raise RedisConnectionError("simulated Redis outage")


async def test_fails_open_when_redis_is_unreachable():
    """A Redis blip must not turn every join/WS-connect/response-submission
    into a hard failure — real-time delivery already degrades when Redis is
    down, so also blocking all traffic on top of that would make an outage
    worse, not safer."""
    redis = _FailingRedis()
    assert await check_rate_limit(redis, "k", limit=5, window_seconds=60) is True


async def test_allows_requests_within_limit():
    redis = _FakeRedis()
    for _ in range(5):
        assert await check_rate_limit(redis, "k", limit=5, window_seconds=60) is True


async def test_rejects_once_limit_is_exceeded():
    redis = _FakeRedis()
    for _ in range(5):
        await check_rate_limit(redis, "k", limit=5, window_seconds=60)
    assert await check_rate_limit(redis, "k", limit=5, window_seconds=60) is False


async def test_sets_expiry_only_on_first_hit():
    redis = _FakeRedis()
    await check_rate_limit(redis, "k", limit=5, window_seconds=60)
    await check_rate_limit(redis, "k", limit=5, window_seconds=60)
    assert redis.expired_keys == ["k"]


async def test_separate_keys_have_independent_limits():
    redis = _FakeRedis()
    for _ in range(5):
        await check_rate_limit(redis, "a", limit=5, window_seconds=60)
    assert await check_rate_limit(redis, "b", limit=5, window_seconds=60) is True


class TestConfigurableJoinRateLimit:
    """JOIN_RATE_LIMIT/JOIN_RATE_LIMIT_WINDOW_SECONDS are Settings fields
    (app/config.py) rather than a hardcoded module constant, so an operator
    can raise them for a workshop behind a single large shared-NAT IP —
    verify the join endpoint actually reads the configured value rather than
    a compiled-in default."""

    async def test_custom_limit_from_settings_is_honored(self, monkeypatch):
        from unittest.mock import AsyncMock, MagicMock

        from httpx import ASGITransport, AsyncClient
        from sqlalchemy.ext.asyncio import AsyncSession

        import app.routers.sessions as sessions_module
        from app.config import Settings
        from app.database import get_db
        from app.main import app

        async def mock_get_db():
            db = AsyncMock(spec=AsyncSession)
            result = MagicMock()
            # No live session for this code — a 404, not a 429, is what
            # "still within budget" looks like from the client's perspective.
            result.unique.return_value.scalar_one_or_none.return_value = None
            db.execute.return_value = result
            yield db

        app.dependency_overrides[get_db] = mock_get_db
        monkeypatch.setattr(
            sessions_module,
            "get_settings",
            lambda: Settings(
                _env_file=None,
                DATABASE_URL="postgresql+asyncpg://test:test@localhost/test",
                SECRET_KEY="test-secret-key",
                INVITE_CODE="TEST-CODE",
                CORS_ORIGINS=["http://testserver"],
                JOIN_RATE_LIMIT=2,
                JOIN_RATE_LIMIT_WINDOW_SECONDS=60,
            ),
        )
        app.state.redis = _FakeRedis()

        transport = ASGITransport(app=app)
        try:
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                for _ in range(2):
                    resp = await client.get("/api/sessions/join/DOES-NOT-EXIST")
                    assert resp.status_code == 404

                resp = await client.get("/api/sessions/join/DOES-NOT-EXIST")
                assert resp.status_code == 429
        finally:
            app.dependency_overrides.pop(get_db, None)
