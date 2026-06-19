"""
Redis-based sliding-window rate limiter.

A Lua script runs atomically on Redis, so the check + increment is safe
under any level of concurrency across multiple API instances.

Falls back to allow (True) when Redis is unreachable, so a Redis outage
degrades gracefully rather than blocking all traffic.
"""
import time
import uuid

# Atomic sliding-window implementation.
# KEYS[1] = rate-limit key
# ARGV[1] = current timestamp (float seconds)
# ARGV[2] = window duration  (seconds)
# ARGV[3] = max allowed requests in the window
# ARGV[4] = unique member (UUID) — prevents ZADD from replacing existing entries
#
# Returns 0 → allowed, 1 → rate-limited.
_SCRIPT = """
local key    = KEYS[1]
local now    = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local max_r  = tonumber(ARGV[3])
local member = ARGV[4]

redis.call('ZREMRANGEBYSCORE', key, '-inf', now - window)
local count = redis.call('ZCARD', key)
if count >= max_r then
    return 1
end
redis.call('ZADD', key, now, member)
redis.call('EXPIRE', key, window + 1)
return 0
"""


async def check_rate_limit(redis, key: str, max_requests: int, window_seconds: int) -> bool:
    """
    Return True if the request is allowed, False if rate-limited.

    Key convention: 'rl:{endpoint}:{identifier}' — callers own the key.
    """
    try:
        result = await redis.eval(
            _SCRIPT,
            1,
            key,
            str(time.time()),
            str(window_seconds),
            str(max_requests),
            str(uuid.uuid4()),
        )
        return result == 0
    except Exception:
        return True  # fail open: never block traffic due to a Redis error
