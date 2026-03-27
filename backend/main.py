import logging
from contextlib import asynccontextmanager

from sqlalchemy import text

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes.execution_routes import router as execution_router
from backend.api.routes.monitor_routes import router as monitor_router
from backend.api.routes.websocket_routes import router as websocket_router
from backend.api.routes.workflow_routes import router as workflow_router
from backend.core.config import settings
from backend.core.database import Base, SessionLocal, engine
from backend.core.time import utc_now
from backend.queue.job_queue import DatabaseJobQueue
from backend.schemas.workflow import HealthResponse, ReadinessResponse
from backend.services.execution_notifier_service import ExecutionNotifierService
from backend.services.execution_service import ExecutionService
from backend.services.migration_service import MigrationService
from backend.services.realtime_service import RealtimeService
from backend.services.seed_service import SeedService
from backend.workers.runtime import WorkerManager


class RuntimeContainer:
    def __init__(self) -> None:
        self.queue = DatabaseJobQueue(SessionLocal)
        self.realtime = RealtimeService()
        self.execution_service = ExecutionService(self.queue, self.realtime)
        self.worker_manager = WorkerManager(self.queue, self.execution_service, SessionLocal)
        self.execution_notifier = ExecutionNotifierService(SessionLocal, self.realtime)


runtime = RuntimeContainer()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        await connection.run_sync(MigrationService.apply)

    async with SessionLocal() as session:
        await SeedService.seed_default_workflows(session)

    app.state.runtime = runtime
    await runtime.execution_notifier.start()
    if settings.inline_workers_enabled:
        await runtime.worker_manager.start()

    yield

    await runtime.worker_manager.stop()
    await runtime.execution_notifier.stop()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/docs" if settings.docs_enabled else None,
    redoc_url="/redoc" if settings.docs_enabled else None,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(workflow_router, prefix=settings.api_prefix)
app.include_router(execution_router, prefix=settings.api_prefix)
app.include_router(monitor_router, prefix=settings.api_prefix)
app.include_router(websocket_router)


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
        timestamp=utc_now(),
    )


@app.get("/health/live", response_model=HealthResponse)
async def live_health() -> HealthResponse:
    return await health()


@app.get("/health/ready", response_model=ReadinessResponse)
async def readiness() -> ReadinessResponse:
    database_status = "ok"
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception as exc:
        logger.exception("Database readiness check failed")
        database_status = f"error: {exc}"

    workers = await runtime.worker_manager.snapshots()
    if not workers:
        worker_status = "not-started"
    elif any(worker.state not in {"offline", "stopped"} for worker in workers):
        worker_status = "running"
    else:
        worker_status = "degraded"
    queue_status = await runtime.queue.stats()
    overall_status = "ok" if database_status == "ok" and worker_status != "degraded" else "degraded"
    return ReadinessResponse(
        status=overall_status,
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
        timestamp=utc_now(),
        database=database_status,
        workers=worker_status,
        queue=queue_status,
    )
