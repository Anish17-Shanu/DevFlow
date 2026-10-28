from __future__ import annotations

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.core.database import Base, get_db_session
from backend.core.rate_limit import rate_limiter
from backend.core.security import hash_api_key
from backend.main import app
from backend.models.entities import ApiKey, Tenant
from backend.queue.job_queue import DatabaseJobQueue
from backend.services.auth_service import _principal_cache
from backend.services.execution_service import ExecutionService
from backend.services.realtime_service import RealtimeService
from backend.workers.runtime import WorkerManager

TENANT_ID = "11111111-1111-1111-1111-111111111111"
OTHER_TENANT_ID = "22222222-2222-2222-2222-222222222222"

ADMIN_KEY = "dvf_test_admin_key_0000000000000000"
OPERATOR_KEY = "dvf_test_operator_key_00000000000000"
VIEWER_KEY = "dvf_test_viewer_key_0000000000000000"
OTHER_ADMIN_KEY = "dvf_test_other_admin_key_000000000000"

API = "/api/v1"


def auth(raw_key: str) -> dict[str, str]:
    return {"X-API-Key": raw_key}


@pytest_asyncio.fixture
async def session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


async def seed_tenants_and_keys(factory) -> None:
    async with factory() as session:
        session.add_all(
            [
                Tenant(id=TENANT_ID, name="Test tenant", slug="test"),
                Tenant(id=OTHER_TENANT_ID, name="Other tenant", slug="other"),
            ]
        )
        for name, raw, role, tenant_id in (
            ("admin", ADMIN_KEY, "admin", TENANT_ID),
            ("operator", OPERATOR_KEY, "operator", TENANT_ID),
            ("viewer", VIEWER_KEY, "viewer", TENANT_ID),
            ("other-admin", OTHER_ADMIN_KEY, "admin", OTHER_TENANT_ID),
        ):
            session.add(
                ApiKey(
                    tenant_id=tenant_id,
                    name=name,
                    prefix=raw[:12],
                    key_hash=hash_api_key(raw),
                    role=role,
                )
            )
        await session.commit()


class TestRuntime:
    """In-process stand-in for RuntimeContainer backed by the test database."""

    def __init__(self, factory) -> None:
        self.queue = DatabaseJobQueue(factory)
        self.realtime = RealtimeService()
        self.execution_service = ExecutionService(self.queue, self.realtime)
        self.worker_manager = WorkerManager(self.queue, self.execution_service, factory)


@pytest_asyncio.fixture
async def runtime(session_factory):
    return TestRuntime(session_factory)


@pytest_asyncio.fixture
async def client(session_factory, runtime):
    await seed_tenants_and_keys(session_factory)
    app.state.runtime = runtime

    async def _session_override():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = _session_override
    _principal_cache.clear()
    if hasattr(rate_limiter, "_buckets"):
        rate_limiter._buckets.clear()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as http_client:
            yield http_client
    finally:
        app.dependency_overrides.clear()
        _principal_cache.clear()


@pytest_asyncio.fixture
async def admin_client(client):
    client.headers.update(auth(ADMIN_KEY))
    return client


async def create_workflow(client, name: str = "sample-flow", tasks: list[dict] | None = None) -> dict:
    response = await client.post(
        f"{API}/workflows",
        headers=auth(ADMIN_KEY),
        json={
            "name": name,
            "tasks": tasks
            or [
                {"name": "extract", "dependencies": [], "config": {"type": "sleep", "duration_ms": 100}},
                {"name": "load", "dependencies": ["extract"], "config": {"type": "sleep", "duration_ms": 100}},
            ],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def drain_queue(runtime: TestRuntime, session_factory, max_jobs: int = 20) -> None:
    """Process queued jobs synchronously, mirroring the worker loop."""
    for index in range(max_jobs):
        job = await runtime.queue.dequeue(worker_id=f"test-worker-{index}", timeout=0)
        if job is None:
            return
        async with session_factory() as session:
            await runtime.execution_service.execute_task(
                session,
                job.execution_task_id,
                f"test-worker-{index}",
                queue_job_id=job.id,
                job=job,
            )
