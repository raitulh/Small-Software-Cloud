import uuid
import typing
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
try:
    from arq.connections import ArqRedis, RedisSettings, create_pool
except ImportError:
    ArqRedis = typing.Any
    RedisSettings = None
    create_pool = None
from app.core.config import settings
from app.db.session import get_db

from app.models import Membership, MembershipRole, User
from app.security import decode_access_token

bearer_scheme = HTTPBearer(auto_error=False)

async def get_current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme), db: AsyncSession = Depends(get_db)) -> User:
    unauthorized = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired access token", headers={"WWW-Authenticate": "Bearer"})
    if credentials is None:
        raise unauthorized
    subject = decode_access_token(credentials.credentials)
    try:
        user_id = uuid.UUID(subject or "")
    except ValueError:
        raise unauthorized from None
    user = await db.scalar(select(User).where(User.id == user_id, User.is_active.is_(True)))
    if user is None:
        raise unauthorized
    return user

async def require_org_membership(organization_id: uuid.UUID, user: User, db: AsyncSession, minimum: MembershipRole = MembershipRole.VIEWER) -> Membership:
    membership = await db.scalar(select(Membership).where(Membership.organization_id == organization_id, Membership.user_id == user.id))
    if membership is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    ranks = {MembershipRole.VIEWER: 0, MembershipRole.DEVELOPER: 1, MembershipRole.ADMIN: 2, MembershipRole.OWNER: 3}
    if ranks[membership.role] < ranks[minimum]:
        raise HTTPException(status_code=403, detail="Insufficient organization permissions")
    return membership

async def get_arq_pool(request: Request) -> ArqRedis:
    pool = getattr(request.app.state, "arq_pool", None)
    if pool is not None:
        return pool
    try:
        return await create_pool(RedisSettings.from_dsn(settings.redis_url))
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Deployment queue is temporarily unavailable") from exc

