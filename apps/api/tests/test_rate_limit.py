import pytest
from fastapi import HTTPException
from app.core.rate_limit import RateLimiter

@pytest.mark.asyncio
async def test_sliding_window_rate_limiter_in_memory():
    limiter = RateLimiter(key_prefix="test_auth", limit=3, window_seconds=10)
    user_ip = "192.168.1.100"

    # First 3 checks succeed without error
    await limiter.check(user_ip, redis=None)
    await limiter.check(user_ip, redis=None)
    await limiter.check(user_ip, redis=None)

    # 4th check must raise HTTPException 429
    with pytest.raises(HTTPException) as excinfo:
        await limiter.check(user_ip, redis=None)
    assert excinfo.value.status_code == 429
    assert "Rate limit exceeded" in excinfo.value.detail
    assert "Retry-After" in excinfo.value.headers

@pytest.mark.asyncio
async def test_rate_limiter_isolated_identifiers():
    limiter = RateLimiter(key_prefix="test_iso", limit=2, window_seconds=10)

    # Exhaust user A
    await limiter.check("user_A", redis=None)
    await limiter.check("user_A", redis=None)
    with pytest.raises(HTTPException):
        await limiter.check("user_A", redis=None)

    # user B is not blocked
    await limiter.check("user_B", redis=None)
