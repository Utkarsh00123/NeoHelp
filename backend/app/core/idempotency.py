import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models import IdempotencyKey

def compute_request_hash(data: Any) -> str:
    if isinstance(data, (dict, list)):
        serialized = json.dumps(data, sort_keys=True, default=str)
    elif data is None:
        serialized = ""
    else:
        serialized = str(data)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

async def check_idempotency(
    db: AsyncSession,
    key: Optional[str],
    user_id: str,
    endpoint: str,
    request_data: Any
) -> Optional[Tuple[int, dict]]:
    if not key:
        return None
    
    req_hash = compute_request_hash(request_data)
    now = datetime.now(timezone.utc)

    query = select(IdempotencyKey).where(
        IdempotencyKey.key == key,
        IdempotencyKey.user_id == user_id
    )
    result = await db.execute(query)
    record = result.scalar_one_or_none()

    if record:
        if record.expires_at > now:
            return record.status_code, record.response_body
    
    return None

async def store_idempotency(
    db: AsyncSession,
    key: Optional[str],
    user_id: str,
    endpoint: str,
    request_data: Any,
    status_code: int,
    response_body: Any
) -> None:
    if not key:
        return
    
    req_hash = compute_request_hash(request_data)
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=24)

    record = IdempotencyKey(
        key=key,
        user_id=user_id,
        endpoint=endpoint,
        request_hash=req_hash,
        status_code=status_code,
        response_body=response_body if isinstance(response_body, (dict, list)) else json.loads(json.dumps(response_body, default=str)),
        expires_at=expires_at,
        created_at=now
    )
    db.add(record)
