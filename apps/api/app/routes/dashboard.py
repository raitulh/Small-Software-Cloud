import uuid
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.db.session import get_db
from app.deps import get_current_user, require_org_membership
from app.models import Deployment, Membership, Organization, Project, Service, User
from app.schemas import (
    DashboardOverview,
    DeploymentRead,
    OrganizationRead,
    ProjectWithServices,
    ServiceSummary,
    UsageSummary,
)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

@router.get("/overview", response_model=DashboardOverview)
async def get_dashboard_overview(
    organization_id: uuid.UUID | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # Determine target organization
    if organization_id:
        membership = await require_org_membership(organization_id, user, db)
        org = await db.get(Organization, organization_id)
        if not org:
            raise HTTPException(status_code=404, detail="Organization not found")
        role_val = membership.role.value if hasattr(membership.role, "value") else str(membership.role)
    else:
        # Pick the user's first organization
        membership_row = await db.execute(
            select(Organization, Membership.role)
            .join(Membership, Membership.organization_id == Organization.id)
            .where(Membership.user_id == user.id)
            .order_by(Organization.created_at.asc())
            .limit(1)
        )
        row = membership_row.first()
        if not row:
            raise HTTPException(status_code=400, detail="No organization is attached to this account")
        org, role_val = row[0], (row[1].value if hasattr(row[1], "value") else str(row[1]))

    org_read = OrganizationRead.model_validate(org)
    org_read.role = role_val

    # Fetch projects for this organization
    projects_res = await db.scalars(
        select(Project)
        .where(Project.organization_id == org.id)
        .order_by(Project.created_at.desc())
    )
    project_models = list(projects_res.all())
    project_ids = [p.id for p in project_models]

    services_by_project: dict[uuid.UUID, list[Service]] = {p.id: [] for p in project_models}
    if project_ids:
        services_res = await db.scalars(
            select(Service)
            .where(Service.project_id.in_(project_ids))
            .order_by(Service.created_at.desc())
        )
        for s in services_res.all():
            services_by_project[s.project_id].append(s)

    all_service_ids = [s.id for services in services_by_project.values() for s in services]
    latest_deployment_by_service: dict[uuid.UUID, Deployment] = {}
    if all_service_ids:
        # Get latest deployment for each service
        recent_deps = await db.scalars(
            select(Deployment)
            .where(Deployment.service_id.in_(all_service_ids))
            .order_by(Deployment.created_at.desc())
            .limit(100)
        )
        for d in recent_deps.all():
            if d.service_id not in latest_deployment_by_service:
                latest_deployment_by_service[d.service_id] = d

    # Build ProjectWithServices list
    projects_output: list[ProjectWithServices] = []
    for p in project_models:
        service_summaries: list[ServiceSummary] = []
        for s in services_by_project.get(p.id, []):
            latest_dep = latest_deployment_by_service.get(s.id)
            dep_read = DeploymentRead.model_validate(latest_dep) if latest_dep else None
            summary = ServiceSummary(
                id=s.id,
                project_id=s.project_id,
                name=s.name,
                slug=s.slug,
                kind=s.kind,
                runtime=s.runtime,
                source_repo=s.source_repo,
                branch=s.branch,
                image_ref=s.image_ref,
                internal_port=s.internal_port,
                memory_mb=s.memory_mb,
                cpu_millicores=s.cpu_millicores,
                status=s.status,
                latest_deployment=dep_read,
                created_at=s.created_at,
                updated_at=s.updated_at
            )
            service_summaries.append(summary)

        p_output = ProjectWithServices(
            id=p.id,
            organization_id=p.organization_id,
            name=p.name,
            slug=p.slug,
            description=p.description,
            created_at=p.created_at,
            updated_at=p.updated_at,
            services=service_summaries
        )
        projects_output.append(p_output)

    # Calculate usage
    total_projects = len(project_models)
    total_services = len(all_service_ids)
    configured_memory = sum(s.memory_mb for services in services_by_project.values() for s in services)
    configured_cpu = sum(s.cpu_millicores for services in services_by_project.values() for s in services)

    since = datetime.now(timezone.utc) - timedelta(days=30)
    deployments_count = 0
    if all_service_ids:
        deployments_count = await db.scalar(
            select(func.count(Deployment.id))
            .where(Deployment.service_id.in_(all_service_ids), Deployment.created_at >= since)
        ) or 0

    usage = UsageSummary(
        projects=total_projects,
        services=total_services,
        deployments_last_30_days=deployments_count,
        configured_memory_mb=configured_memory,
        configured_cpu_millicores=configured_cpu,
        deployment_driver=settings.deployment_driver
    )

    # Recent deployments across organization
    recent_deployments: list[DeploymentRead] = []
    if all_service_ids:
        deps_res = await db.scalars(
            select(Deployment)
            .where(Deployment.service_id.in_(all_service_ids))
            .order_by(Deployment.created_at.desc())
            .limit(10)
        )
        recent_deployments = [DeploymentRead.model_validate(d) for d in deps_res.all()]

    return DashboardOverview(
        organization=org_read,
        projects=projects_output,
        usage=usage,
        recent_deployments=recent_deployments
    )
