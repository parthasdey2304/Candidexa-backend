from __future__ import annotations
import time
import redis.asyncio as redis
from fastapi import HTTPException, Request, status
from app.core.config import settings

_pool = redis.ConnectionPool.from_url(settings.REDIS_URL, decode_responses=True)

def _client() -> redis.Redis:
    return redis.Redis(connection_pool=_pool)

# Sliding-window Lua - atomic, multi-window safe.
_LUA = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local id = ARGV[4]

redis.call('ZREMRANGEBYSCORE', key, 0, now - window)
local count = redis.call('ZCARD', key)
if count >= limit then
  return 0
end
redis.call('ZADD', key, now, id)
redis.call('PEXPIRE', key, window)
return 1
"""


async def rate_limit(key: str, limit_per_min: int) -> None:
    r = _client()
    now = int(time.time() * 1000)
    import uuid
    unique_id = f"{now}:{uuid.uuid4().hex[:8]}"
    res = await r.eval(_LUA, 1, key, now, 60_000, limit_per_min, unique_id)
    if int(res) == 0:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="rate_limit_exceeded",
            headers={"Retry-After": "60"},
        )


def ip_key(request: Request, bucket: str) -> str:
    ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or request.client.host
    return f"rl:{bucket}:ip:{ip}"


def user_key(user_id: str, bucket: str) -> str:
    return f"rl:{bucket}:user:{user_id}"