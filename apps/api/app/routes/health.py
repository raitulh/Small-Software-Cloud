from fastapi import APIRouter, HTTPException
from redis.asyncio import Redis
from sqlalchemy import text
from app.core.config import settings
from app.db.session import AsyncSessionLocal

router = APIRouter(tags=["health"])

@router.get("/health/live")
async def liveness():
    return {"status": "alive", "service": settings.app_name}

@router.get("/health/ready")
async def readiness():
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        redis = Redis.from_url(settings.redis_url, socket_connect_timeout=1, socket_timeout=1)
        try: await redis.ping()
        finally: await redis.aclose()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="A required dependency is unavailable") from exc
    return {"status": "ready", "driver": settings.deployment_driver}
