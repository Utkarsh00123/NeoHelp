from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import asyncio
from contextlib import asynccontextmanager
from app.config import settings
from app.api.health import router as health_router
from app.api.auth import router as auth_router
from app.api.items import router as items_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup actions
    print(f"Starting {settings.PROJECT_NAME} in {settings.ENVIRONMENT} mode...")
    try:
        from app.seed import seed_database
        await seed_database(2500)
    except Exception as e:
        print(f"Warning: Database seeding encountered an error: {e}")

    # Optional: Run outbox worker inside API process for single-service free tier hosting
    worker_task = None
    if settings.RUN_WORKER_IN_APP:
        try:
            from app.worker import run_worker
            worker_task = asyncio.create_task(run_worker())
            print("Background Outbox Worker started inside API process.")
        except Exception as e:
            print(f"Warning: Failed to start background worker inside app: {e}")

    yield

    # Shutdown actions
    if worker_task:
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass
    print("Shutting down NeoHelp API...")

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Operational task coordination, incident resolution, and compliance tracking platform with rich event chronology.",
    version="0.1.0",
    lifespan=lifespan
)

# Setup CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_origin_regex=".*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health_router, prefix="/api")
app.include_router(auth_router, prefix="/api")
app.include_router(items_router, prefix="/api")

@app.get("/")
async def root():
    return {
        "app": settings.PROJECT_NAME,
        "version": "0.1.0",
        "docs": "/docs",
        "health": "/api/health"
    }
