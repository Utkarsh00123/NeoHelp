from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.database import get_db
from app.config import settings
import redis.asyncio as aioredis

router = APIRouter(prefix="/health", tags=["Health"])

@router.get("")
async def health_check(db: AsyncSession = Depends(get_db)):
    db_status = "healthy"
    redis_status = "healthy"
    
    # Check Postgres
    try:
        await db.execute(text("SELECT 1"))
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"
    
    # Check Redis
    try:
        redis_url = settings.normalized_redis_url
        redis_kwargs = {"decode_responses": True}
        if redis_url.startswith("rediss://"):
            redis_kwargs["ssl_cert_reqs"] = None
        r = aioredis.from_url(redis_url, **redis_kwargs)
        await r.ping()
        await r.aclose()
    except Exception as e:
        redis_status = f"unhealthy: {str(e)}"
        
    is_healthy = (db_status == "healthy" and redis_status == "healthy")
    
    response = {
        "status": "healthy" if is_healthy else "degraded",
        "service": settings.PROJECT_NAME,
        "environment": settings.ENVIRONMENT,
        "database": db_status,
        "redis": redis_status,
    }
    
    if not is_healthy:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=response
        )
        
    return response

@router.get("/ping")
async def ping():
    return {"status": "pong"}
