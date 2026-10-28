from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

from backend.core.config import settings


@dataclass
class _Bucket:
    tokens: float
    updated_at: float


class MemoryRateLimiter:
    def __init__(self, rate_per_minute: int, burst: int) -> None:
        self.rate = rate_per_minute / 60.0
        self.burst = float(burst)
        self._buckets: dict[str, _Bucket] = {}
        self._lock = asyncio.Lock()

    async def consume(self, key: str) -> tuple[bool, float]:
        now = time.monotonic()
        async with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = _Bucket(tokens=self.burst, updated_at=now)
                self._buckets[key] = bucket
            elapsed = max(0.0, now - bucket.updated_at)
            bucket.tokens = min(self.burst, bucket.tokens + elapsed * self.rate)
            bucket.updated_at = now
            if bucket.tokens < 1.0:
                retry_after = (1.0 - bucket.tokens) / self.rate if self.rate else 60.0
                return False, round(retry_after, 2)
            bucket.tokens -= 1.0
            if len(self._buckets) > 10_000:
                cutoff = now - 600
                self._buckets = {k: v for k, v in self._buckets.items() if v.updated_at >= cutoff}
            return True, 0.0


class RedisRateLimiter:
    def __init__(self, client) -> None:
        self._client = client
        self.rate = settings.rate_limit_requests_per_minute / 60.0
        self.burst = float(settings.rate_limit_burst)

    async def consume(self, key: str) -> tuple[bool, float]:
        now = time.time()
        redis_key = f"devflow:ratelimit:{key}"
        bucket = await self._client.hgetall(redis_key)
        tokens = float(bucket.get("tokens", self.burst)) if bucket else self.burst
        updated_at = float(bucket.get("updated_at", now)) if bucket else now
        tokens = min(self.burst, tokens + max(0.0, now - updated_at) * self.rate)
        if tokens < 1.0:
            retry_after = (1.0 - tokens) / self.rate if self.rate else 60.0
            return False, round(retry_after, 2)
        tokens -= 1.0
        pipe = self._client.pipeline()
        pipe.hset(redis_key, mapping={"tokens": tokens, "updated_at": now})
        pipe.expire(redis_key, 600)
        await pipe.execute()
        return True, 0.0


def build_rate_limiter():
    if settings.rate_limit_backend == "redis" and settings.redis_url:
        try:
            import redis.asyncio as redis

            return RedisRateLimiter(redis.from_url(settings.redis_url, decode_responses=True))
        except Exception:
            pass
    return MemoryRateLimiter(settings.rate_limit_requests_per_minute, settings.rate_limit_burst)


rate_limiter = build_rate_limiter()
