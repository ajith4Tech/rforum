"""Unit tests for app/rate_limit.py's shared fixed-window counter — no
Postgres or real Redis needed, just the incr/expire surface it depends on."""
import pytest

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
