import pytest
import uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import NullPool
import redis.asyncio as aioredis

from app.config import settings
from app.models import OutboxJob
from app.worker import process_single_job

@pytest.mark.asyncio
async def test_outbox_job_processing_and_completion():
    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)

    test_dedupe = f"test-job-{uuid.uuid4()}"
    now = datetime.now(timezone.utc)

    async with session_factory() as session:
        job = OutboxJob(
            id=str(uuid.uuid4()),
            dedupe_key=test_dedupe,
            payload={"event": "item_created", "item_id": "test-item-123"},
            status="PENDING",
            attempts=0,
            max_attempts=3,
            next_run_at=now
        )
        session.add(job)
        await session.commit()
        job_id = job.id

    async with session_factory() as session:
        job = (await session.execute(select(OutboxJob).where(OutboxJob.id == job_id))).scalar_one()
        success = await process_single_job(session, job, redis_client)
        assert success is True
        assert job.status == "COMPLETED"
        assert job.last_error is None

    # Verify second execution is deduplicated idempotently
    async with session_factory() as session:
        job = (await session.execute(select(OutboxJob).where(OutboxJob.id == job_id))).scalar_one()
        job.status = "PENDING"
        await session.commit()

        # Re-run: should hit Redis dedupe cache and immediately mark COMPLETED
        success2 = await process_single_job(session, job, redis_client)
        assert success2 is True
        assert job.status == "COMPLETED"

    await redis_client.aclose()
    await engine.dispose()

@pytest.mark.asyncio
async def test_outbox_job_retry_backoff_and_failure_cap():
    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    
    # Mock redis client that raises an exception when publishing to simulate network failure
    class FailingRedis:
        async def get(self, key):
            return None
        async def publish(self, channel, message):
            raise ConnectionError("Simulated Redis network connection drop")
        async def setex(self, key, ttl, val):
            pass

    failing_redis = FailingRedis()
    now = datetime.now(timezone.utc)
    job_id = str(uuid.uuid4())

    async with session_factory() as session:
        job = OutboxJob(
            id=job_id,
            dedupe_key=f"failing-job-{uuid.uuid4()}",
            payload={"event": "item_assigned", "item_id": "fail-test-item"},
            status="PENDING",
            attempts=0,
            max_attempts=3,
            next_run_at=now
        )
        session.add(job)
        await session.commit()

    # Attempt 1: Should fail, increment attempt to 1, backoff 2 seconds
    async with session_factory() as session:
        job = (await session.execute(select(OutboxJob).where(OutboxJob.id == job_id))).scalar_one()
        success = await process_single_job(session, job, failing_redis)
        assert success is False
        assert job.attempts == 1
        assert job.status == "PENDING"
        assert job.last_error is not None
        assert job.next_run_at > now + timedelta(seconds=1)

    # Attempt 2: Should fail, increment attempt to 2, backoff 4 seconds
    async with session_factory() as session:
        job = (await session.execute(select(OutboxJob).where(OutboxJob.id == job_id))).scalar_one()
        success = await process_single_job(session, job, failing_redis)
        assert success is False
        assert job.attempts == 2
        assert job.status == "PENDING"
        assert job.next_run_at > now + timedelta(seconds=3)

    # Attempt 3: Should fail, hit max_attempts (3), transition to FAILED permanently
    async with session_factory() as session:
        job = (await session.execute(select(OutboxJob).where(OutboxJob.id == job_id))).scalar_one()
        success = await process_single_job(session, job, failing_redis)
        assert success is False
        assert job.attempts == 3
        assert job.status == "FAILED"
        assert "Simulated Redis network connection drop" in job.last_error

    await engine.dispose()
