import uuid
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.db.session import get_db
from app.deps import get_current_user, require_org_membership
from app.models import Deployment, Membership, Organization, Project, Service, User
from app.schemas import UsageSummary

router = APIRouter(prefix="/usage", tags=["usage"])

@router.get("", response_model=UsageSummary)
async def usage_summary(
    organization_id: uuid.UUID | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if organization_id:
        await require_org_membership(organization_id, user, db)
        org = await db.get(Organization, organization_id)
    else:
        org = await db.scalar(
            select(Organization)
            .join(Membership, Membership.organization_id == Organization.id)
            .where(Membership.user_id == user.id)
            .order_by(Organization.created_at.asc())
            .limit(1)
        )
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")

    projects = await db.scalar(select(func.count(Project.id)).where(Project.organization_id == org.id)) or 0
    services = await db.scalar(select(func.count(Service.id)).join(Project, Service.project_id == Project.id).where(Project.organization_id == org.id)) or 0
    memory = await db.scalar(select(func.coalesce(func.sum(Service.memory_mb), 0)).join(Project, Service.project_id == Project.id).where(Project.organization_id == org.id)) or 0
    cpu = await db.scalar(select(func.coalesce(func.sum(Service.cpu_millicores), 0)).join(Project, Service.project_id == Project.id).where(Project.organization_id == org.id)) or 0
    since = datetime.now(timezone.utc) - timedelta(days=30)
    deployments = await db.scalar(select(func.count(Deployment.id)).join(Service, Deployment.service_id == Service.id).join(Project, Service.project_id == Project.id).where(Project.organization_id == org.id, Deployment.created_at >= since)) or 0
    return UsageSummary(projects=projects, services=services, deployments_last_30_days=deployments, configured_memory_mb=memory, configured_cpu_millicores=cpu, deployment_driver=settings.deployment_driver)
