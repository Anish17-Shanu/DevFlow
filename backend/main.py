from __future__ import annotations

import logging
import re
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.api.routes.auth_routes import router as auth_router
from backend.api.routes.execution_routes import router as execution_router
from backend.api.routes.monitor_routes import router as monitor_router
from backend.api.routes.ops_routes import router as ops_router
from backend.api.routes.websocket_routes import router as websocket_router
from backend.api.routes.workflow_routes import router as workflow_router
from backend.core.config import settings
from backend.core.context import binding
from backend.core.context import request_id as request_id_context
from backend.core.database import SessionLocal, engine
from backend.core.logging import setup_logging
from backend.core.metrics import HTTP_LATENCY, HTTP_REQUESTS
from backend.core.security import ApiError
from backend.core.time import utc_now
from backend.core.tracing import setup_tracing
from backend.queue.job_queue import DatabaseJobQueue
from backend.schemas.common import ErrorResponse
from backend.schemas.workflow import HealthResponse, ReadinessResponse
from backend.services.auth_service import AuthService
from backend.services.execution_service import ExecutionService
from backend.services.migration_service import MigrationService
from backend.services.outbox_notifier_service import OutboxNotifierService
from backend.services.realtime_bus import build_realtime_bus
from backend.services.realtime_service import RealtimeService
from backend.services.retention_service import RetentionService
from backend.services.scheduler_service import SchedulerService
from backend.services.seed_service import SeedService
from backend.services.watchdog_service import WatchdogService
from backend.services.webhook_service import WebhookDispatcherService
from backend.workers.runtime import WorkerManager

logger = logging.getLogger(__name__)
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{8,64}$")
STATUS_CODES = {
    400: "invalid_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    413: "payload_too_large",
    422: "validation_error",
    429: "rate_limited",
    500: "internal_error",
    503: "unavailable",
}


class RuntimeContainer:
    def __init__(self) -> None:
        self.queue = DatabaseJobQueue(SessionLocal)
        self.realtime = RealtimeService()
        self.execution_service = ExecutionService(self.queue, self.realtime)
        self.worker_manager = WorkerManager(self.queue, self.execution_service, SessionLocal)
        self.notifier = OutboxNotifierService(SessionLocal, self.realtime)
        self.webhooks = WebhookDispatcherService(SessionLocal)
        self.watchdog = WatchdogService(SessionLocal, self.queue, self.execution_service)
        self.scheduler = SchedulerService(SessionLocal, self.execution_service)
        self.retention = RetentionService(SessionLocal)


runtime = RuntimeContainer()


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    if settings.auto_migrate:
        await MigrationService.upgrade()

    async with SessionLocal() as session:
        principal = await AuthService(session).ensure_bootstrap()
        await SeedService.seed_default_workflows(session, principal.tenant_id)

    app.state.runtime = runtime
    bus = build_realtime_bus()
    if bus is not None:
        try:
            await bus.start(runtime.realtime.broadcast_local)
        except Exception:
            logger.exception("Realtime bus failed to start; falling back to local-only websocket delivery.")
            bus = None
        else:
            runtime.realtime.use_bus(bus)
    await runtime.notifier.start()
    await runtime.webhooks.start()
    await runtime.watchdog.start()
    await runtime.scheduler.start()
    await runtime.retention.start()
    if settings.inline_workers_enabled:
        await runtime.worker_manager.start()

    try:
        yield
    finally:
        if settings.inline_workers_enabled:
            await runtime.worker_manager.stop()
        await runtime.retention.stop()
        await runtime.scheduler.stop()
        await runtime.watchdog.stop()
        await runtime.webhooks.stop()
        await runtime.notifier.stop()
        if bus is not None:
            await bus.stop()
            runtime.realtime.use_bus(None)
        await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/docs" if settings.docs_enabled else None,
    redoc_url="/redoc" if settings.docs_enabled else None,
    responses={401: {"model": ErrorResponse}, 429: {"model": ErrorResponse}},
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "Retry-After"],
)
setup_tracing(app)


@app.middleware("http")
async def harden_responses(request: Request, call_next):
    incoming_request_id = request.headers.get("x-request-id", "")
    request_id = incoming_request_id if REQUEST_ID_PATTERN.match(incoming_request_id) else uuid.uuid4().hex
    request.state.request_id = request_id
    token = request_id_context.set(request_id)

    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            length = int(content_length)
        except ValueError:
            return _error_response(400, "invalid_request", "Invalid Content-Length header.", request_id)
        if length > settings.max_request_body_bytes:
            return _error_response(413, "payload_too_large", "Request body too large.", request_id)

    started = time.perf_counter()
    status_code = 500
    with binding(request_id=request_id):
        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception:
            logger.exception("Unhandled error while processing %s %s", request.method, request.url.path)
            response = _error_response(500, "internal_error", "Internal server error.", request_id)
            status_code = 500
        finally:
            elapsed = time.perf_counter() - started
            route = request.scope.get("route")
            path = getattr(route, "path", None) or ("unmatched" if status_code == 404 else request.url.path)
            HTTP_REQUESTS.labels(method=request.method, path=path, status=str(status_code)).inc()
            HTTP_LATENCY.labels(method=request.method, path=path).observe(elapsed)
            logger.info(
                "request_completed",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": status_code,
                    "duration_ms": round(elapsed * 1000, 2),
                },
            )
    request_id_context.reset(token)

    response.headers.setdefault("X-Request-ID", request_id)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Cache-Control", "no-store")
    response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
    if settings.is_production:
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


def _error_response(
    status_code: int,
    code: str,
    message: str,
    request_id: str,
    details=None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    response_headers = {"X-Request-ID": request_id}
    if headers:
        response_headers.update(headers)
    return JSONResponse(
        status_code=status_code,
        content={"code": code, "message": message, "request_id": request_id, "details": details},
        headers=response_headers,
    )


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", None) or request_id_context.get()


@app.exception_handler(ApiError)
async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    return _error_response(exc.status_code, exc.code, exc.message, _request_id(request), exc.details, exc.headers)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    message = exc.detail if isinstance(exc.detail, str) else "Request failed."
    code = STATUS_CODES.get(exc.status_code, "error")
    return _error_response(exc.status_code, code, message, _request_id(request))


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    details = []
    for error in exc.errors():
        details.append(
            {
                "loc": [str(part) for part in error.get("loc", [])],
                "msg": error.get("msg", "Invalid value."),
                "type": error.get("type", "value_error"),
            }
        )
    return _error_response(422, "validation_error", "Request validation failed.", _request_id(request), details)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error while processing %s %s", request.method, request.url.path)
    return _error_response(500, "internal_error", "Internal server error.", _request_id(request))


app.include_router(auth_router, prefix=settings.api_prefix)
app.include_router(workflow_router, prefix=settings.api_prefix)
app.include_router(execution_router, prefix=settings.api_prefix)
app.include_router(monitor_router, prefix=settings.api_prefix)
app.include_router(ops_router, prefix=settings.api_prefix)
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
        database_status = f"error: {exc.__class__.__name__}"

    workers = await runtime.worker_manager.snapshots()
    if not workers:
        worker_status = "not-started"
    elif any(worker.state not in {"offline", "stopped"} for worker in workers):
        worker_status = "running"
    else:
        worker_status = "degraded"
    queue_status = await runtime.queue.stats()
    unhealthy_workers = settings.is_production and worker_status != "running"
    overall_status = (
        "ok" if database_status == "ok" and queue_status["healthy"] and not unhealthy_workers else "degraded"
    )
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


@app.get("/metrics", include_in_schema=False)
async def metrics() -> Response:
    if not settings.metrics_enabled:
        return Response(status_code=404)
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
