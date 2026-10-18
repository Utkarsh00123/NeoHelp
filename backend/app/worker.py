import asyncio
import signal
import sys
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, update, and_
import redis.asyncio as aioredis

from app.database import AsyncSessionLocal
from app.config import settings
from app.models import OutboxJob

running = True

def handle_exit(signum, frame):
    global running
    print(f"Received exit signal {signum}. Shutting down worker gracefully...")
    running = False

async def process_single_job(session, job: OutboxJob, redis_client: aioredis.Redis) -> bool:
    """Processes an outbox job idempotently."""
    now = datetime.now(timezone.utc)
    
    # Idempotency check via Redis dedupe_key cache (TTL 24 hours)
    redis_dedupe_key = f"processed_outbox:{job.dedupe_key}"
    already_processed = await redis_client.get(redis_dedupe_key)
    if already_processed:
        print(f"[Worker] Dedupe skip: Job {job.id} ({job.dedupe_key}) already processed.")
        job.status = "COMPLETED"
        job.updated_at = now
        await session.commit()
        return True

    # Mark as PROCESSING
    job.status = "PROCESSING"
    job.updated_at = now
    await session.commit()

    try:
        # Simulate secondary task / mocked notification
        payload = job.payload
        event_type = payload.get("event", "unknown")
        item_id = payload.get("item_id", "unknown")
        
        print(f"[Worker] Processing Outbox Job: {job.id} | Event: {event_type} | Item: {item_id}")
        
        # Publish event to Redis channel for live monitoring
        await redis_client.publish(
            "neohelp:operational_events",
            f"event={event_type}&item_id={item_id}"
        )

        # Mark as COMPLETED
        job.status = "COMPLETED"
        job.updated_at = datetime.now(timezone.utc)
        job.last_error = None
        
        # Mark dedupe key in Redis for 24h
        await redis_client.setex(redis_dedupe_key, 86400, "1")
        await session.commit()
        print(f"[Worker] Job {job.id} completed successfully.")
        return True

    except Exception as exc:
        job.attempts += 1
        job.last_error = str(exc)
        job.updated_at = datetime.now(timezone.utc)

        if job.attempts >= job.max_attempts:
            job.status = "FAILED"
            print(f"[Worker] Job {job.id} failed permanently after {job.attempts} attempts: {exc}")
        else:
            # Exponential backoff: 2 ** attempts seconds
            backoff_seconds = 2 ** job.attempts
            job.status = "PENDING"
            job.next_run_at = datetime.now(timezone.utc) + timedelta(seconds=backoff_seconds)
            print(f"[Worker] Job {job.id} failed (attempt {job.attempts}/{job.max_attempts}). Backoff {backoff_seconds}s: {exc}")

        await session.commit()
        return False

async def run_worker():
    global running
    print(f"Starting NeoHelp Outbox Worker (Redis: {settings.REDIS_URL})...")
    redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)

    try:
        while running:
            processed_any = False
            async with AsyncSessionLocal() as session:
                now = datetime.now(timezone.utc)
                # Fetch pending jobs whose next_run_at has arrived
                stmt = (
                    select(OutboxJob)
                    .where(
                        and_(
                            OutboxJob.status.in_(["PENDING", "PROCESSING"]),
                            OutboxJob.next_run_at <= now,
                            OutboxJob.attempts < OutboxJob.max_attempts
                        )
                    )
                    .with_for_update(skip_locked=True)
                    .limit(10)
                )
                res = await session.execute(stmt)
                jobs = res.scalars().all()

                for job in jobs:
                    await process_single_job(session, job, redis_client)
                    processed_any = True

            if not processed_any and running:
                await asyncio.sleep(1)

    finally:
        await redis_client.aclose()
        print("Outbox Worker shut down cleanly.")

if __name__ == "__main__":
    signal.signal(signal.SIGTERM, handle_exit)
    signal.signal(signal.SIGINT, handle_exit)
    asyncio.run(run_worker())
