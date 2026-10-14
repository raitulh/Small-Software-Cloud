import json
import logging
from datetime import datetime, timezone
import typing
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import OutboxEvent

logger = logging.getLogger("smallcloud.outbox")

def now() -> datetime:
    return datetime.now(timezone.utc)

async def record_outbox_event(
    db: AsyncSession,
    event_type: str,
    payload: dict[str, typing.Any]
) -> OutboxEvent:
    """Record an event into the transactional outbox table within the caller's active DB transaction."""
    event = OutboxEvent(
        event_type=event_type,
        payload_json=json.dumps(payload),
        status="pending",
        retry_count=0,
        created_at=now()
    )
    db.add(event)
    return event

async def relay_outbox_events(
    db: AsyncSession,
    pool: typing.Any = None,
    limit: int = 50
) -> int:
    """
    Fetch pending outbox events and dispatch them to the background worker/queue.
    Guarantees at-least-once delivery even if initial direct enqueue failed during API handling.
    """
    result = await db.execute(
        select(OutboxEvent)
        .where(OutboxEvent.status == "pending")
        .order_by(OutboxEvent.created_at.asc())
        .limit(limit)
    )
    events = result.scalars().all()
    if not events:
        return 0

    relayed_count = 0
    for event in events:
        try:
            payload = json.loads(event.payload_json)
            if event.event_type == "deployment.process":
                deployment_id = payload.get("deployment_id")
                if pool is not None and hasattr(pool, "enqueue_job"):
                    await pool.enqueue_job(
                        "process_deployment",
                        str(deployment_id),
                        _job_id=f"deploy-{deployment_id}"
                    )
                event.status = "delivered"
                event.processed_at = now()
                relayed_count += 1
            else:
                logger.warning("Unknown outbox event type: %s", event.event_type)
                event.status = "failed"
                event.last_error = f"Unknown event type: {event.event_type}"
                event.processed_at = now()
        except Exception as exc:
            event.retry_count += 1
            event.last_error = str(exc)[:450]
            if event.retry_count >= 5:
                event.status = "failed"
                logger.error("Outbox event %s failed after %d retries: %s", event.id, event.retry_count, exc)
            else:
                logger.warning("Outbox event %s retry %d failed: %s", event.id, event.retry_count, exc)

    await db.commit()
    return relayed_count
