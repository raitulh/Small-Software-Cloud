import asyncio
from datetime import datetime, timezone
import re
import secrets
import typing
import uuid
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
try:
    from arq.connections import ArqRedis
except ImportError:
    ArqRedis = typing.Any
from app.core.config import settings
from app.db.session import get_db
from app.deps import get_arq_pool, get_current_user, require_org_membership
from app.models import Deployment, DeploymentLog, DeploymentStatus, Membership, MembershipRole, Project, Service, User
from app.schemas import DeploymentRead, ServiceCreate, ServiceRead, ServiceUpdate
from app.services.audit import record_audit
from app.services.outbox import record_outbox_event

router = APIRouter(tags=["services"])

def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:64] or "service"

@router.get("/projects/{project_id}/services", response_model=list[ServiceRead])
async def list_services(project_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    await require_org_membership(project.organization_id, user, db)
    result = await db.scalars(select(Service).where(Service.project_id == project.id).order_by(Service.created_at.desc()))
    return list(result.all())

@router.post("/projects/{project_id}/services", response_model=ServiceRead, status_code=status.HTTP_201_CREATED)
async def create_service(project_id: uuid.UUID, payload: ServiceCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    await require_org_membership(project.organization_id, user, db, MembershipRole.DEVELOPER)

    count = await db.scalar(
        select(func.count(Service.id))
        .join(Project, Service.project_id == Project.id)
        .where(Project.organization_id == project.organization_id)
    ) or 0
    if count >= settings.max_services_per_org:
        raise HTTPException(status_code=429, detail="Organization service quota reached")

    if payload.memory_mb and payload.memory_mb > settings.max_service_memory_mb:
        raise HTTPException(status_code=422, detail="Requested memory exceeds the configured per-service maximum")
    if payload.cpu_millicores and payload.cpu_millicores > settings.max_service_cpu_millicores:
        raise HTTPException(status_code=422, detail="Requested CPU exceeds the configured per-service maximum")
    if payload.runtime.value == "docker_image" and not payload.image_ref:
        raise HTTPException(status_code=422, detail="docker_image runtime requires an image_ref")
    if payload.runtime.value != "docker_image" and not payload.source_repo:
        raise HTTPException(status_code=422, detail="A supported HTTPS source_repo is required for this runtime")

    slug = payload.slug or slugify(payload.name)
    if await db.scalar(select(Service.id).where(Service.project_id == project.id, Service.slug == slug)):
        raise HTTPException(status_code=409, detail="A service with this slug already exists in the project")

    service = Service(
        project_id=project.id,
        name=payload.name,
        slug=slug,
        kind=payload.kind,
        runtime=payload.runtime,
        source_repo=payload.source_repo,
        branch=payload.branch,
        image_ref=payload.image_ref,
        internal_port=payload.internal_port,
        memory_mb=payload.memory_mb or settings.default_service_memory_mb,
        cpu_millicores=payload.cpu_millicores or settings.default_service_cpu_millicores,
        deploy_token=f"sct_{secrets.token_urlsafe(32)}"
    )
    try:
        db.add(service)
        await db.flush()
        await record_audit(db, project.organization_id, user.id, "service.created", "service", str(service.id), {"slug": slug, "runtime": service.runtime.value})
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="A service with this slug already exists in the project") from exc

    await db.refresh(service)
    return service

@router.get("/services/{service_id}", response_model=ServiceRead)
async def get_service(service_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    service = await db.get(Service, service_id)
    if service is None:
        raise HTTPException(status_code=404, detail="Service not found")
    project = await db.get(Project, service.project_id)
    await require_org_membership(project.organization_id, user, db)
    return service

@router.patch("/services/{service_id}", response_model=ServiceRead)
async def update_service(
    service_id: uuid.UUID,
    payload: ServiceUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    service = await db.get(Service, service_id)
    if service is None:
        raise HTTPException(status_code=404, detail="Service not found")
    project = await db.get(Project, service.project_id)
    await require_org_membership(project.organization_id, user, db, MembershipRole.DEVELOPER)

    if payload.memory_mb is not None:
        if payload.memory_mb > settings.max_service_memory_mb:
            raise HTTPException(status_code=422, detail="Requested memory exceeds the configured per-service maximum")
        service.memory_mb = payload.memory_mb
    if payload.cpu_millicores is not None:
        if payload.cpu_millicores > settings.max_service_cpu_millicores:
            raise HTTPException(status_code=422, detail="Requested CPU exceeds the configured per-service maximum")
        service.cpu_millicores = payload.cpu_millicores
    if payload.name is not None:
        service.name = payload.name
    if payload.branch is not None:
        service.branch = payload.branch
    if payload.source_repo is not None:
        service.source_repo = payload.source_repo
    if payload.image_ref is not None:
        service.image_ref = payload.image_ref
    if payload.internal_port is not None:
        service.internal_port = payload.internal_port

    await record_audit(db, project.organization_id, user.id, "service.updated", "service", str(service.id))
    await db.commit()
    await db.refresh(service)
    return service

@router.delete("/services/{service_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_service(service_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    service = await db.get(Service, service_id)
    if service is None:
        raise HTTPException(status_code=404, detail="Service not found")
    project = await db.get(Project, service.project_id)
    await require_org_membership(project.organization_id, user, db, MembershipRole.ADMIN)
    await record_audit(db, project.organization_id, user.id, "service.deleted", "service", str(service.id))
    await db.delete(service)
    await db.commit()

@router.post("/services/{service_id}/deploy-token", response_model=ServiceRead)
async def generate_deploy_token(
    service_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    service = await db.get(Service, service_id)
    if service is None:
        raise HTTPException(status_code=404, detail="Service not found")
    project = await db.get(Project, service.project_id)
    await require_org_membership(project.organization_id, user, db, MembershipRole.DEVELOPER)

    service.deploy_token = f"sct_{secrets.token_urlsafe(32)}"
    await record_audit(db, project.organization_id, user.id, "service.deploy_token_generated", "service", str(service.id))
    await db.commit()
    await db.refresh(service)
    return service

@router.post("/services/{service_id}/deploy-hook", response_model=DeploymentRead, status_code=status.HTTP_202_ACCEPTED)
async def trigger_deploy_hook(
    service_id: uuid.UUID,
    request: Request,
    token: str | None = Query(default=None),
    x_deploy_token: str | None = Header(default=None, alias="X-Deploy-Token"),
    db: AsyncSession = Depends(get_db),
    pool: ArqRedis = Depends(get_arq_pool)
):
    service = await db.get(Service, service_id)
    if service is None:
        raise HTTPException(status_code=404, detail="Service not found")

    provided_token = token or x_deploy_token
    if not provided_token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            provided_token = auth_header[7:].strip()

    if not service.deploy_token or not provided_token or not secrets.compare_digest(service.deploy_token, provided_token):
        raise HTTPException(status_code=401, detail="Invalid or missing deploy webhook token")

    project = await db.get(Project, service.project_id)
    owner_membership = await db.scalar(
        select(Membership)
        .where(Membership.organization_id == project.organization_id, Membership.role == MembershipRole.OWNER)
        .limit(1)
    )
    requester_id = owner_membership.user_id if owner_membership else project.organization_id

    deployment = Deployment(service_id=service.id, requested_by=requester_id, status=DeploymentStatus.QUEUED)
    db.add(deployment)
    service.status = "deploying"
    await db.flush()

    db.add(DeploymentLog(deployment_id=deployment.id, level="INFO", message="Deployment triggered via external webhook/deploy hook."))
    outbox_event = await record_outbox_event(db, "deployment.process", {"deployment_id": str(deployment.id)})
    await db.commit()
    await db.refresh(deployment)

    if pool is not None and hasattr(pool, "enqueue_job"):
        try:
            await pool.enqueue_job("process_deployment", str(deployment.id), _job_id=f"deploy-{deployment.id}")
            outbox_event.status = "delivered"
            outbox_event.processed_at = datetime.now(timezone.utc)
            await db.commit()
        except Exception:
            db.add(DeploymentLog(deployment_id=deployment.id, level="WARN", message="Immediate queue dispatch deferred; outbox relay will dispatch shortly."))
            await db.commit()

    return deployment

@router.get("/services/{service_id}/runtime-logs")
async def get_runtime_logs(
    service_id: uuid.UUID,
    tail: int = Query(default=100, ge=10, le=1000),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    service = await db.get(Service, service_id)
    if service is None:
        raise HTTPException(status_code=404, detail="Service not found")
    project = await db.get(Project, service.project_id)
    await require_org_membership(project.organization_id, user, db, MembershipRole.VIEWER)

    if settings.deployment_driver in {"docker", "local_docker"}:
        container_name = f"sc-{str(service.id)[:12]}"
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", "logs", "--tail", str(tail), container_name,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            output = (stdout.decode("utf-8", errors="replace") + "\n" + stderr.decode("utf-8", errors="replace")).strip()
            lines = [line for line in output.split("\n") if line]
            return {"container": container_name, "driver": "docker", "logs": lines}
        except Exception as exc:
            return {"container": container_name, "driver": "docker", "logs": [f"Could not retrieve runtime logs: {exc}"]}
    else:
        return {
            "container": f"sc-{str(service.id)[:12]}",
            "driver": "mock",
            "logs": [
                f"[SIMULATION] Container sc-{str(service.id)[:12]} runtime stdout stream.",
                f"[INFO] Service '{service.name}' listening on port {service.internal_port} (mock mode active).",
                "[INFO] Workload simulation active; no real container process is running."
            ]
        }
