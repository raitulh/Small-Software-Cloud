import json
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import AuditEvent

async def record_audit(db: AsyncSession, organization_id: uuid.UUID, actor_user_id: uuid.UUID | None,
                       action: str, target_type: str, target_id: str, metadata: dict | None = None) -> None:
    db.add(AuditEvent(organization_id=organization_id, actor_user_id=actor_user_id,
                      action=action, target_type=target_type, target_id=target_id,
                      metadata_json=json.dumps(metadata or {}, separators=(",", ":"))))
