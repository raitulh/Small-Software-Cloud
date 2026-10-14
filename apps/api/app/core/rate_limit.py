import time
from fastapi import HTTPException, Request, status
from redis.asyncio import Redis

class RateLimiter:
    """Sliding-window rate limiter using Redis with an automatic in-memory fallback."""
    def __init__(self, key_prefix: str, limit: int, window_seconds: int):
        self.key_prefix = key_prefix
        self.limit = limit
        self.window_seconds = window_seconds
        self._memory_cache: dict[str, list[float]] = {}

    async def check(self, identifier: str, redis: Redis | None = None) -> None:
        key = f"rl:{self.key_prefix}:{identifier}"
        now = time.time()

        if redis is not None:
            try:
                pipe = redis.pipeline()
                pipe.zadd(key, {str(now): now})
                pipe.zremrangebyscore(key, 0, now - self.window_seconds)
                pipe.zcard(key)
                pipe.expire(key, self.window_seconds + 5)
                _, _, count, _ = await pipe.execute()

                if count > self.limit:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail=f"Rate limit exceeded. Try again in {self.window_seconds} seconds.",
                        headers={"Retry-After": str(self.window_seconds)}
                    )
                return
            except HTTPException:
                raise
            except Exception:
                pass

        # In-memory sliding window fallback
        timestamps = self._memory_cache.get(key, [])
        cutoff = now - self.window_seconds
        timestamps = [t for t in timestamps if t > cutoff]
        if len(timestamps) >= self.limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Try again in {self.window_seconds} seconds.",
                headers={"Retry-After": str(self.window_seconds)}
            )
        timestamps.append(now)
        self._memory_cache[key] = timestamps

login_limiter = RateLimiter(key_prefix="login", limit=5, window_seconds=60)
register_limiter = RateLimiter(key_prefix="register", limit=3, window_seconds=60)

def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
