from redis.asyncio import Redis


async def check_rate_limit(redis: Redis, key: str, limit: int, window_seconds: int) -> bool:
    """
    Fixed-window counter: increment `key`, starting its TTL on the first hit
    in the window. Returns True if the caller is still within `limit`, False
    if they should be rejected. Same technique already used ad hoc in
    app/routers/responses.py, shared here so every rate-limited endpoint
    (WS connect, join-by-code, login, register) uses one implementation.
    """
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, window_seconds)
    return count <= limit
