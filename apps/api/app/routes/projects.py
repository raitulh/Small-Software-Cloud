import re
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.db.session import get_db
from app.deps import get_current_user, require_org_membership
from app.models import Membership, MembershipRole, Organization, Project, User
from app.schemas import ProjectCreate, ProjectRead, ProjectUpdate
from app.services.audit import record_audit

router = APIRouter(prefix="/projects", tags=["projects"])

def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:64] or "project"

async def owned_organizations(db: AsyncSession, user_id: uuid.UUID):
    result = await db.execute(
        select(Organization)
        .join(Membership, Membership.organization_id == Organization.id)
        .where(Membership.user_id == user_id)
        .order_by(Organization.created_at.asc())
    )
    return list(result.scalars().all())

@router.get("", response_model=list[ProjectRead])
async def list_projects(
    organization_id: uuid.UUID | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if organization_id:
        await require_org_membership(organization_id, user, db, MembershipRole.VIEWER)
        query = select(Project).where(Project.organization_id == organization_id).order_by(Project.created_at.desc())
    else:
        orgs = await owned_organizations(db, user.id)
        if not orgs:
            return []
        query = select(Project).where(Project.organization_id.in_([o.id for o in orgs])).order_by(Project.created_at.desc())

    result = await db.scalars(query)
    return list(result.all())

@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def create_project(payload: ProjectCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if payload.organization_id:
        target_org_id = payload.organization_id
        await require_org_membership(target_org_id, user, db, MembershipRole.DEVELOPER)
    else:
        orgs = await owned_organizations(db, user.id)
        if not orgs:
            raise HTTPException(status_code=400, detail="No organization is attached to this account")
        target_org_id = orgs[0].id
        await require_org_membership(target_org_id, user, db, MembershipRole.DEVELOPER)

    count = await db.scalar(select(func.count(Project.id)).where(Project.organization_id == target_org_id)) or 0
    if count >= settings.max_projects_per_org:
        raise HTTPException(status_code=429, detail="Organization project quota reached")

    slug = payload.slug or slugify(payload.name)
    if await db.scalar(select(Project.id).where(Project.organization_id == target_org_id, Project.slug == slug)):
        raise HTTPException(status_code=409, detail="A project with this slug already exists in the organization")

    project = Project(organization_id=target_org_id, name=payload.name, slug=slug, description=payload.description)
    try:
        db.add(project)
        await db.flush()
        await record_audit(db, target_org_id, user.id, "project.created", "project", str(project.id), {"slug": slug})
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="A project with this slug already exists in the organization") from exc

    await db.refresh(project)
    return project

@router.get("/{project_id}", response_model=ProjectRead)
async def get_project(project_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    await require_org_membership(project.organization_id, user, db, MembershipRole.VIEWER)
    return project

@router.patch("/{project_id}", response_model=ProjectRead)
async def update_project(
    project_id: uuid.UUID,
    payload: ProjectUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    await require_org_membership(project.organization_id, user, db, MembershipRole.DEVELOPER)

    if payload.name is not None:
        project.name = payload.name
    if payload.description is not None:
        project.description = payload.description

    await record_audit(db, project.organization_id, user.id, "project.updated", "project", str(project.id))
    await db.commit()
    await db.refresh(project)
    return project

@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    await require_org_membership(project.organization_id, user, db, MembershipRole.ADMIN)

    await record_audit(db, project.organization_id, user.id, "project.deleted", "project", str(project.id))
    await db.delete(project)
    await db.commit()
