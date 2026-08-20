"""Redis-backed rate limiting for production deployments.

This module provides distributed rate limiting using Redis, suitable for
multi-instance deployments on Railway/Render.
"""

import time
from typing import Optional, Tuple

import redis.asyncio as redis

from app.core.config import settings


class RateLimiter:
    """Distributed rate limiter using Redis sorted sets."""

    def __init__(self, redis_url: str):
        self._client: Optional[redis.Redis] = None
        self._redis_url = redis_url

    async def _get_client(self) -> redis.Redis:
        if self._client is None:
            self._client = redis.from_url(
                self._redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
        return self._client

    async def close(self) -> None:
        if self._client:
            await self._client.close()
            self._client = None

    async def check_limit(
        self,
        key: str,
        limit: int,
        window_seconds: int,
    ) -> Tuple[bool, int]:
        """Check if the key is within rate limits.
        
        Returns (allowed, retry_after_seconds).
        """
        client = await self._get_client()
        now = time.time()
        window_start = now - window_seconds
        
        # Use a sorted set with timestamps as scores
        pipe = client.pipeline()
        pipe.zremrangebyscore(key, 0, window_start)
        pipe.zcard(key)
        pipe.zadd(key, {f"{now}": now})
        pipe.expire(key, window_seconds + 1)
        results = await pipe.execute()
        
        current_count = results[1]
        
        if current_count >= limit:
            # Get the oldest entry to calculate retry-after
            oldest = await client.zrange(key, 0, 0, withscores=True)
            if oldest:
                oldest_time = oldest[0][1]
                retry_after = max(1, int(oldest_time + window_seconds - now))
            else:
                retry_after = window_seconds
            return False, retry_after
        
        return True, 0


# Global rate limiter instance (initialized on startup)
_rate_limiter: Optional[RateLimiter] = None


async def get_rate_limiter() -> Optional[RateLimiter]:
    """Get the global rate limiter instance."""
    return _rate_limiter


async def init_rate_limiter() -> None:
    """Initialize the global rate limiter."""
    global _rate_limiter
    if settings.REDIS_URL:
        _rate_limiter = RateLimiter(settings.REDIS_URL)


async def close_rate_limiter() -> None:
    """Close the global rate limiter."""
    global _rate_limiter
    if _rate_limiter:
        await _rate_limiter.close()
        _rate_limiter = None