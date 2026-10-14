import asyncio
import json
import uuid
import typing
from datetime import datetime, timedelta, timezone
try:
    from arq.connections import ArqRedis
except ImportError:
    ArqRedis = typing.Any
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.db.session import AsyncSessionLocal, get_db

from app.deps import bearer_scheme, get_arq_pool, get_current_user, require_org_membership
from app.models import Deployment, DeploymentLog, DeploymentStatus, MembershipRole, Project, Service, User
from app.schemas import DeploymentLogRead, DeploymentRead
from app.security import decode_access_token
from app.services.audit import record_audit
from app.services.outbox import record_outbox_event


router = APIRouter(tags=["deployments"])

@router.post("/services/{service_id}/deployments", response_model=DeploymentRead, status_code=status.HTTP_202_ACCEPTED)
async def create_deployment(
    service_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    pool: ArqRedis = Depends(get_arq_pool)
):
    service = await db.get(Service, service_id)
    if service is None:
        raise HTTPException(status_code=404, detail="Service not found")
    project = await db.get(Project, service.project_id)
    await require_org_membership(project.organization_id, user, db, MembershipRole.DEVELOPER)

    since = datetime.now(timezone.utc) - timedelta(hours=1)
    count = await db.scalar(
        select(func.count(Deployment.id))
        .join(Service, Deployment.service_id == Service.id)
        .join(Project, Service.project_id == Project.id)
        .where(Project.organization_id == project.organization_id, Deployment.created_at >= since)
    ) or 0
    if count >= settings.max_deployments_per_org_per_hour:
        raise HTTPException(status_code=429, detail="Deployment rate limit reached for this organization")

    deployment = Deployment(service_id=service.id, requested_by=user.id, status=DeploymentStatus.QUEUED)
    db.add(deployment)
    service.status = "deploying"
    await db.flush()

    db.add(DeploymentLog(deployment_id=deployment.id, level="INFO", message="Deployment request accepted and queued."))
    await record_audit(db, project.organization_id, user.id, "deployment.requested", "deployment", str(deployment.id), {"service_id": str(service.id)})
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

@router.get("/services/{service_id}/deployments", response_model=list[DeploymentRead])
async def list_deployments(service_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    service = await db.get(Service, service_id)
    if service is None:
        raise HTTPException(status_code=404, detail="Service not found")
    project = await db.get(Project, service.project_id)
    await require_org_membership(project.organization_id, user, db)
    result = await db.scalars(select(Deployment).where(Deployment.service_id == service_id).order_by(Deployment.created_at.desc()).limit(50))
    return list(result.all())

@router.get("/deployments/{deployment_id}", response_model=DeploymentRead)
async def get_deployment(deployment_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    deployment = await db.get(Deployment, deployment_id)
    if deployment is None:
        raise HTTPException(status_code=404, detail="Deployment not found")
    service = await db.get(Service, deployment.service_id)
    project = await db.get(Project, service.project_id)
    await require_org_membership(project.organization_id, user, db)
    return deployment

@router.post("/deployments/{deployment_id}/cancel", response_model=DeploymentRead)
async def cancel_deployment(deployment_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    deployment = await db.get(Deployment, deployment_id)
    if deployment is None:
        raise HTTPException(status_code=404, detail="Deployment not found")
    service = await db.get(Service, deployment.service_id)
    project = await db.get(Project, service.project_id)
    await require_org_membership(project.organization_id, user, db, MembershipRole.DEVELOPER)

    if deployment.status in {DeploymentStatus.HEALTHY, DeploymentStatus.FAILED, DeploymentStatus.CANCELED}:
        raise HTTPException(status_code=400, detail=f"Cannot cancel a deployment in {deployment.status.value} status")

    deployment.status = DeploymentStatus.CANCELED
    deployment.finished_at = datetime.now(timezone.utc)
    if service.status == "deploying":
        service.status = "canceled"
    db.add(DeploymentLog(deployment_id=deployment.id, level="WARN", message="Deployment was canceled by user."))
    await record_audit(db, project.organization_id, user.id, "deployment.canceled", "deployment", str(deployment.id))
    await db.commit()
    await db.refresh(deployment)
    return deployment

@router.get("/deployments/{deployment_id}/logs", response_model=list[DeploymentLogRead])
async def get_deployment_logs(deployment_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    deployment = await db.get(Deployment, deployment_id)
    if deployment is None:
        raise HTTPException(status_code=404, detail="Deployment not found")
    service = await db.get(Service, deployment.service_id)
    project = await db.get(Project, service.project_id)
    await require_org_membership(project.organization_id, user, db)
    result = await db.scalars(select(DeploymentLog).where(DeploymentLog.deployment_id == deployment_id).order_by(DeploymentLog.created_at.asc()).limit(1000))
    return list(result.all())

@router.get("/deployments/{deployment_id}/logs/stream")
async def stream_deployment_logs(
    deployment_id: uuid.UUID,
    token: str | None = Query(default=None),
    credentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db)
):
    current_user = None
    if credentials and credentials.credentials:
        sub = decode_access_token(credentials.credentials)
        if sub:
            try:
                current_user = await db.scalar(select(User).where(User.id == uuid.UUID(sub), User.is_active.is_(True)))
            except ValueError:
                pass
    if not current_user and token:
        sub = decode_access_token(token)
        if sub:
            try:
                current_user = await db.scalar(select(User).where(User.id == uuid.UUID(sub), User.is_active.is_(True)))
            except ValueError:
                pass

    if not current_user:
        raise HTTPException(status_code=401, detail="Invalid or expired access token")

    deployment = await db.get(Deployment, deployment_id)
    if deployment is None:
        raise HTTPException(status_code=404, detail="Deployment not found")
    service = await db.get(Service, deployment.service_id)
    project = await db.get(Project, service.project_id)
    await require_org_membership(project.organization_id, current_user, db)


    async def log_generator():
        last_log_time = datetime.fromtimestamp(0, tz=timezone.utc)
        terminal_states = {DeploymentStatus.HEALTHY, DeploymentStatus.FAILED, DeploymentStatus.CANCELED}

        for _ in range(300):  # Stream up to 2.5 minutes
            async with AsyncSessionLocal() as session:
                logs_res = await session.scalars(
                    select(DeploymentLog)
                    .where(DeploymentLog.deployment_id == deployment_id, DeploymentLog.created_at > last_log_time)
                    .order_by(DeploymentLog.created_at.asc())
                )
                new_logs = list(logs_res.all())
                for log_entry in new_logs:
                    last_log_time = log_entry.created_at
                    data = {
                        "id": str(log_entry.id),
                        "level": log_entry.level,
                        "message": log_entry.message,
                        "created_at": log_entry.created_at.isoformat()
                    }
                    yield f"data: {json.dumps(data)}\n\n"

                dep = await session.get(Deployment, deployment_id)
                if dep and dep.status in terminal_states:
                    yield f"event: done\ndata: {json.dumps({'status': dep.status.value, 'output_url': dep.output_url})}\n\n"
                    break

            await asyncio.sleep(0.5)

    return StreamingResponse(log_generator(), media_type="text/event-stream")

