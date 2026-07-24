import logging

from redis.asyncio import Redis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)


async def check_rate_limit(redis: Redis, key: str, limit: int, window_seconds: int) -> bool:
    """
    Fixed-window counter: increment `key`, starting its TTL on the first hit
    in the window. Returns True if the caller is still within `limit`, False
    if they should be rejected. Same technique already used ad hoc in
    app/routers/responses.py, shared here so every rate-limited endpoint
    (WS connect, join-by-code, login, register) uses one implementation.

    Fails open on a Redis error instead of propagating it: a transient Redis
    blip already degrades real-time delivery (WS pub/sub depends on the same
    Redis), so also turning it into a hard failure on every join/WS-connect/
    response-submission attempt would compound the outage rather than
    contain it.
    """
    try:
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, window_seconds)
    except RedisError:
        logger.warning("rate_limit_check_failed key=%s — failing open", key, exc_info=True)
        return True
    return count <= limit
