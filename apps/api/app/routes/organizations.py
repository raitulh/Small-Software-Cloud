import re
import secrets
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.deps import get_current_user, require_org_membership
from app.models import Membership, MembershipRole, Organization, User
from app.schemas import MemberRead, OrganizationCreate, OrganizationRead
from app.services.audit import record_audit

router = APIRouter(prefix="/organizations", tags=["organizations"])

def org_slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:50] or f"team-{secrets.token_hex(4)}"

@router.get("", response_model=list[OrganizationRead])
async def list_organizations(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    results = await db.execute(
        select(Organization, Membership.role)
        .join(Membership, Membership.organization_id == Organization.id)
        .where(Membership.user_id == user.id)
        .order_by(Organization.created_at.asc())
    )
    org_list = []
    for org, role in results.all():
        data = OrganizationRead.model_validate(org)
        data.role = role.value if hasattr(role, "value") else str(role)
        org_list.append(data)
    return org_list

@router.post("", response_model=OrganizationRead, status_code=status.HTTP_201_CREATED)
async def create_organization(payload: OrganizationCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    name = payload.name.strip()
    base_slug = payload.slug or org_slug(name)
    slug = base_slug
    for _ in range(5):
        if not await db.scalar(select(Organization.id).where(Organization.slug == slug)):
            break
        slug = f"{base_slug[:53]}-{secrets.token_hex(2)}"

    org = Organization(name=name, slug=slug)
    try:
        db.add(org)
        await db.flush()
        db.add(Membership(organization_id=org.id, user_id=user.id, role=MembershipRole.OWNER))
        await record_audit(db, org.id, user.id, "organization.created", "organization", str(org.id), {"name": name, "slug": slug})
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="An organization with this slug already exists") from exc

    await db.refresh(org)
    res = OrganizationRead.model_validate(org)
    res.role = MembershipRole.OWNER.value
    return res

@router.get("/{organization_id}", response_model=OrganizationRead)
async def get_organization(organization_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    membership = await require_org_membership(organization_id, user, db, MembershipRole.VIEWER)
    org = await db.get(Organization, organization_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    res = OrganizationRead.model_validate(org)
    res.role = membership.role.value if hasattr(membership.role, "value") else str(membership.role)
    return res

@router.get("/{organization_id}/members", response_model=list[MemberRead])
async def list_members(organization_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await require_org_membership(organization_id, user, db, MembershipRole.VIEWER)
    results = await db.execute(
        select(Membership, User.email)
        .join(User, Membership.user_id == User.id)
        .where(Membership.organization_id == organization_id)
        .order_by(Membership.created_at.asc())
    )
    members = []
    for membership, email in results.all():
        role_str = membership.role.value if hasattr(membership.role, "value") else str(membership.role)
        members.append(MemberRead(
            id=membership.id,
            organization_id=membership.organization_id,
            user_id=membership.user_id,
            role=role_str,
            email=email,
            created_at=membership.created_at
        ))
    return members
