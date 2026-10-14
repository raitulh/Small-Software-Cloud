import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.deps import get_current_user, require_org_membership
from app.models import MembershipRole, Project, Service, ServiceEnvVar, User
from app.schemas import EnvVarBulkUpdate, EnvVarRawImport, EnvVarRead
from app.services.audit import record_audit

router = APIRouter(tags=["environment_variables"])

@router.get("/services/{service_id}/env", response_model=list[EnvVarRead])
async def list_env_vars(
    service_id: uuid.UUID,
    reveal: bool = Query(default=False),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    service = await db.get(Service, service_id)
    if service is None:
        raise HTTPException(status_code=404, detail="Service not found")
    project = await db.get(Project, service.project_id)
    await require_org_membership(project.organization_id, user, db, MembershipRole.VIEWER)

    vars_result = await db.scalars(
        select(ServiceEnvVar)
        .where(ServiceEnvVar.service_id == service_id)
        .order_by(ServiceEnvVar.key.asc())
    )
    result = []
    for var in vars_result.all():
        val = var.value if (not var.is_secret or reveal) else "••••••••"
        result.append(EnvVarRead(key=var.key, value=val, is_secret=var.is_secret))
    return result

@router.put("/services/{service_id}/env", response_model=list[EnvVarRead])
async def update_env_vars(
    service_id: uuid.UUID,
    payload: EnvVarBulkUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    service = await db.get(Service, service_id)
    if service is None:
        raise HTTPException(status_code=404, detail="Service not found")
    project = await db.get(Project, service.project_id)
    await require_org_membership(project.organization_id, user, db, MembershipRole.DEVELOPER)

    # Clean existing variables for service
    await db.execute(delete(ServiceEnvVar).where(ServiceEnvVar.service_id == service_id))

    # Insert new variables
    created = []
    for item in payload.variables:
        key = item.key.strip()
        if not key:
            continue
        env_record = ServiceEnvVar(
            service_id=service_id,
            key=key,
            value=item.value,
            is_secret=item.is_secret
        )
        db.add(env_record)
        created.append(env_record)

    await record_audit(
        db, project.organization_id, user.id, "service.env_updated",
        "service", str(service_id), {"count": len(created)}
    )
    await db.commit()

    return [EnvVarRead(key=v.key, value=v.value, is_secret=v.is_secret) for v in created]

@router.post("/services/{service_id}/env/raw", response_model=list[EnvVarRead])
async def import_raw_env(
    service_id: uuid.UUID,
    payload: EnvVarRawImport,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Parse a raw .env text string, auto-detect secret keys (passwords, tokens, keys),
    and store or merge them into the service's environment configuration.
    """
    service = await db.get(Service, service_id)
    if service is None:
        raise HTTPException(status_code=404, detail="Service not found")
    project = await db.get(Project, service.project_id)
    await require_org_membership(project.organization_id, user, db, MembershipRole.DEVELOPER)

    secret_keywords = ("KEY", "SECRET", "PASSWORD", "PASS", "TOKEN", "AUTH", "CREDENTIAL", "PRIVATE")
    parsed_items: dict[str, tuple[str, bool]] = {}

    for line in payload.raw_env.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip()
        if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
            val = val[1:-1]
        if not key:
            continue
        is_sec = any(kw in key.upper() for kw in secret_keywords)
        parsed_items[key] = (val, is_sec)

    if not payload.merge:
        await db.execute(delete(ServiceEnvVar).where(ServiceEnvVar.service_id == service_id))
    else:
        # Delete existing rows that match the incoming keys so we can insert new values
        if parsed_items:
            await db.execute(
                delete(ServiceEnvVar)
                .where(ServiceEnvVar.service_id == service_id, ServiceEnvVar.key.in_(list(parsed_items.keys())))
            )

    created = []
    for k, (v, is_sec) in parsed_items.items():
        env_record = ServiceEnvVar(
            service_id=service_id,
            key=k,
            value=v,
            is_secret=is_sec
        )
        db.add(env_record)
        created.append(env_record)

    await record_audit(
        db, project.organization_id, user.id, "service.env_raw_imported",
        "service", str(service_id), {"count": len(created), "merged": payload.merge}
    )
    await db.commit()

    # Return full current list of variables for this service
    all_vars = (await db.scalars(
        select(ServiceEnvVar)
        .where(ServiceEnvVar.service_id == service_id)
        .order_by(ServiceEnvVar.key.asc())
    )).all()

    return [EnvVarRead(key=v.key, value=v.value, is_secret=v.is_secret) for v in all_vars]
