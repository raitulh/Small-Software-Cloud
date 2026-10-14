import json
import uuid
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from app.db.base import Base
from app.services.outbox import record_outbox_event, relay_outbox_events

class MockArqRedis:
    def __init__(self, should_fail: bool = False):
        self.enqueued_jobs = []
        self.should_fail = should_fail

    async def enqueue_job(self, function_name: str, *args, **kwargs):
        if self.should_fail:
            raise RuntimeError("Redis connection error")
        self.enqueued_jobs.append((function_name, args, kwargs))

@pytest.fixture
async def async_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()

@pytest.mark.asyncio
async def test_record_outbox_event(async_db: AsyncSession):
    did = str(uuid.uuid4())
    event = await record_outbox_event(async_db, "deployment.process", {"deployment_id": did})
    await async_db.commit()

    assert event.id is not None
    assert event.event_type == "deployment.process"
    assert event.status == "pending"
    assert event.retry_count == 0
    payload = json.loads(event.payload_json)
    assert payload["deployment_id"] == did

@pytest.mark.asyncio
async def test_relay_outbox_events_success(async_db: AsyncSession):
    did = str(uuid.uuid4())
    await record_outbox_event(async_db, "deployment.process", {"deployment_id": did})
    await async_db.commit()

    mock_pool = MockArqRedis(should_fail=False)
    count = await relay_outbox_events(async_db, pool=mock_pool)
    assert count == 1
    assert len(mock_pool.enqueued_jobs) == 1
    assert mock_pool.enqueued_jobs[0][0] == "process_deployment"
    assert mock_pool.enqueued_jobs[0][1][0] == did

    # Verifying status became delivered
    refreshed_count = await relay_outbox_events(async_db, pool=mock_pool)
    assert refreshed_count == 0  # No more pending events

@pytest.mark.asyncio
async def test_relay_outbox_events_failure_retry(async_db: AsyncSession):
    did = str(uuid.uuid4())
    event = await record_outbox_event(async_db, "deployment.process", {"deployment_id": did})
    await async_db.commit()

    failing_pool = MockArqRedis(should_fail=True)
    count = await relay_outbox_events(async_db, pool=failing_pool)
    assert count == 0

    await async_db.refresh(event)
    assert event.status == "pending"
    assert event.retry_count == 1
    assert "Redis connection error" in event.last_error
