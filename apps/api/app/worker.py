from datetime import datetime, timedelta, timezone
import logging
import typing
import uuid
from sqlalchemy import select
try:
    from arq import cron
    from arq.connections import RedisSettings
except ImportError:
    cron = None
    RedisSettings = typing.Any
from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models import Deployment, DeploymentLog, DeploymentStatus, Service, ServiceEnvVar
from app.services.deploy_driver import get_deployment_driver

logger = logging.getLogger("smallcloud.worker")
def now(): return datetime.now(timezone.utc)

async def process_deployment(ctx, deployment_id: str):
    """Idempotent deployment handler. Executes via configured driver (mock or docker)."""
    did = uuid.UUID(deployment_id)
    async with AsyncSessionLocal() as db:
        deployment = await db.get(Deployment, did)
        if deployment is None:
            return {"ok": False, "reason": "not_found"}
        if deployment.status in {DeploymentStatus.HEALTHY, DeploymentStatus.FAILED, DeploymentStatus.CANCELED}:
            return {"ok": True, "skipped": True, "status": deployment.status.value}

        service = await db.get(Service, deployment.service_id)
        if service is None:
            deployment.status = DeploymentStatus.FAILED
            deployment.error_code = "SERVICE_MISSING"
            deployment.error_message = "Service no longer exists"
            deployment.finished_at = now()
            await db.commit()
            return {"ok": False, "reason": "service_missing"}

        # Fetch environment variables for the service
        env_rows = await db.scalars(select(ServiceEnvVar).where(ServiceEnvVar.service_id == service.id))
        env_vars = {row.key: row.value for row in env_rows.all()}

        deployment.status = DeploymentStatus.BUILDING
        deployment.started_at = deployment.started_at or now()
        db.add(DeploymentLog(deployment_id=did, level="INFO", message="Deployment worker claimed the job."))
        db.add(DeploymentLog(deployment_id=did, level="INFO", message=f"Driver selected: {settings.deployment_driver}."))
        await db.commit()

        async def log_callback(level: str, message: str):
            db.add(DeploymentLog(deployment_id=did, level=level, message=message))
            await db.commit()

        try:
            driver = get_deployment_driver()
            deployment.status = DeploymentStatus.STARTING
            service.status = "deploying"
            await db.commit()

            result = await driver.deploy(
                service_id=str(service.id),
                service_slug=service.slug,
                deployment_id=str(did),
                runtime=service.runtime.value,
                kind=service.kind.value,
                source_repo=service.source_repo,
                branch=service.branch,
                image_ref=service.image_ref,
                internal_port=service.internal_port,
                memory_mb=service.memory_mb,
                cpu_millicores=service.cpu_millicores,
                env_vars=env_vars,
                log_callback=log_callback
            )

            deployment.status = DeploymentStatus.HEALTHY
            deployment.image_digest = result.image_digest
            deployment.output_url = result.output_url
            deployment.finished_at = now()
            service.status = "healthy"
            service.current_deployment_id = deployment.id

            await db.commit()
            return {"ok": True, "status": deployment.status.value, "url": result.output_url}

        except Exception as exc:
            logger.exception("Deployment failed id=%s", deployment_id)
            deployment.status = DeploymentStatus.FAILED
            deployment.error_code = "DEPLOYMENT_FAILED"
            deployment.error_message = str(exc)[:500] if settings.cloud_env != "production" else "Deployment execution failed."
            deployment.finished_at = now()
            service.status = "failed"
            db.add(DeploymentLog(deployment_id=did, level="ERROR", message=f"Deployment error: {str(exc)[:300]}"))
            await db.commit()
            raise

async def reconcile_stale_deployments(ctx):
    """Periodic self-healing job: recovers or marks failed any deployments stranded in non-terminal states beyond timeout."""
    timeout_threshold = now() - timedelta(seconds=settings.deployment_job_timeout_seconds)
    async with AsyncSessionLocal() as db:
        stale_deps = await db.scalars(
            select(Deployment)
            .where(
                Deployment.status.in_([DeploymentStatus.QUEUED, DeploymentStatus.BUILDING, DeploymentStatus.STARTING]),
                Deployment.created_at < timeout_threshold
            )
        )
        count = 0
        for dep in stale_deps.all():
            dep.status = DeploymentStatus.FAILED
            dep.error_code = "TIMEOUT_EXCEEDED"
            dep.error_message = f"Execution exceeded timeout limit ({settings.deployment_job_timeout_seconds}s)"
            dep.finished_at = now()
            db.add(DeploymentLog(deployment_id=dep.id, level="ERROR", message="Deployment timed out and was reconciled by worker."))
            service = await db.get(Service, dep.service_id)
            if service and service.status == "deploying":
                service.status = "failed"
            count += 1
        if count > 0:
            await db.commit()
            logger.warning("Reconciled %d stale deployment(s)", count)

async def relay_outbox_cron(ctx):
    """Periodic job to dispatch pending outbox events to the queue."""
    redis_pool = ctx.get("redis") if isinstance(ctx, dict) else None
    async with AsyncSessionLocal() as db:
        from app.services.outbox import relay_outbox_events
        count = await relay_outbox_events(db, pool=redis_pool, limit=50)
        if count > 0:
            logger.info("Relayed %d outbox event(s) to worker queue", count)

async def monitor_services_health(ctx):
    """Periodic watchdog inspecting healthy services; detects crashes or container termination."""
    if settings.deployment_driver not in {"docker", "local_docker"}:
        return

    import asyncio
    async with AsyncSessionLocal() as db:
        services = (await db.scalars(select(Service).where(Service.status == "healthy"))).all()
        for svc in services:
            container_name = f"sc-{str(svc.id)[:12]}"
            try:
                proc = await asyncio.create_subprocess_exec(
                    "docker", "inspect", "--format", "{{.State.Status}}", container_name,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, _ = await proc.communicate()
                status_text = stdout.decode("utf-8").strip().lower()
                if status_text in {"exited", "dead"}:
                    svc.status = "crashed"
                    logger.warning("Service %s container %s is %s; marking as crashed", svc.slug, container_name, status_text)
            except Exception as exc:
                logger.debug("Container inspect check error for %s: %s", container_name, exc)
        await db.commit()

async def startup(ctx):
    logger.info("Worker started; driver=%s", settings.deployment_driver)
    try:
        await relay_outbox_cron(ctx)
    except Exception as exc:
        logger.warning("Initial outbox relay check error: %s", exc)

async def shutdown(ctx):
    logger.info("Worker shutting down")

class WorkerSettings:
    functions = [process_deployment, reconcile_stale_deployments, relay_outbox_cron, monitor_services_health]
    cron_jobs = [
        cron(reconcile_stale_deployments, minute=None, second=0),
        cron(relay_outbox_cron, minute=None, second=15),
        cron(monitor_services_health, minute=None, second=45),
    ] if cron else []
    redis_settings = RedisSettings.from_dsn(settings.redis_url) if hasattr(RedisSettings, "from_dsn") else None
    max_jobs = 4
    job_timeout = settings.deployment_job_timeout_seconds
    max_tries = 3
    on_startup = startup
    on_shutdown = shutdown
