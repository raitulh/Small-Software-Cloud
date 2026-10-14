import re
import secrets
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.rate_limit import get_client_ip, login_limiter, register_limiter
from app.db.session import get_db
from app.models import Membership, MembershipRole, Organization, User
from app.schemas import TokenRead, UserCreate, UserLogin, UserRead
from app.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["authentication"])

def org_slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:50] or f"team-{secrets.token_hex(4)}"

async def token_response(user: User) -> TokenRead:
    token, expires = create_access_token(str(user.id))
    return TokenRead(access_token=token, expires_in=expires, user=UserRead.model_validate(user))

@router.post("/register", response_model=TokenRead, status_code=status.HTTP_201_CREATED)
async def register(payload: UserCreate, request: Request, db: AsyncSession = Depends(get_db)):
    client_ip = get_client_ip(request)
    await register_limiter.check(client_ip)

    if not settings.allow_signups:
        raise HTTPException(status_code=403, detail="New registrations are temporarily disabled")
    email = payload.email.lower().strip()
    if await db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    user = User(email=email, password_hash=hash_password(payload.password))
    try:
        db.add(user)
        await db.flush()
        base = org_slug(payload.organization_name or email.split("@", 1)[0])
        slug = base
        for _ in range(5):
            if not await db.scalar(select(Organization.id).where(Organization.slug == slug)):
                break
            slug = f"{base[:53]}-{secrets.token_hex(2)}"
        org = Organization(name=(payload.organization_name or f"{email.split('@', 1)[0]}'s workspace")[:120], slug=slug)
        db.add(org)
        await db.flush()
        db.add(Membership(organization_id=org.id, user_id=user.id, role=MembershipRole.OWNER))
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Account or workspace identifier conflict; try another email or workspace name") from exc
    await db.refresh(user)
    return await token_response(user)

@router.post("/login", response_model=TokenRead)
async def login(payload: UserLogin, request: Request, db: AsyncSession = Depends(get_db)):
    email = payload.email.lower().strip()
    client_ip = get_client_ip(request)
    await login_limiter.check(f"{client_ip}:{email}")

    user = await db.scalar(select(User).where(User.email == email, User.is_active.is_(True)))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect email or password", headers={"WWW-Authenticate": "Bearer"})
    return await token_response(user)
