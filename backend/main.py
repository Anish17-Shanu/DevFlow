from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes.execution_routes import router as execution_router
from backend.api.routes.monitor_routes import router as monitor_router
from backend.api.routes.websocket_routes import router as websocket_router
from backend.api.routes.workflow_routes import router as workflow_router
from backend.core.config import settings
from backend.core.database import Base, SessionLocal, engine
from backend.queue.job_queue import InMemoryJobQueue
from backend.services.execution_service import ExecutionService
from backend.services.realtime_service import RealtimeService
from backend.services.seed_service import SeedService
from backend.workers.runtime import WorkerManager


class RuntimeContainer:
    def __init__(self) -> None:
        self.queue = InMemoryJobQueue()
        self.realtime = RealtimeService()
        self.execution_service = ExecutionService(self.queue, self.realtime)
        self.worker_manager = WorkerManager(self.queue, self.execution_service)


runtime = RuntimeContainer()


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with SessionLocal() as session:
        await SeedService.seed_default_workflows(session)

    app.state.runtime = runtime
    if settings.inline_workers_enabled:
        await runtime.worker_manager.start()

    yield

    await runtime.worker_manager.stop()


app = FastAPI(title=settings.app_name, lifespan=lifespan)
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


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": settings.app_name}
