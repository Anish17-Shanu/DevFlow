from __future__ import annotations

import asyncio
import os
import time
import uuid

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.core.database import Base
from backend.models import entities  # noqa: F401
from backend.models.entities import Tenant
from backend.queue.job_queue import DatabaseJobQueue, QueueJob
from backend.services.realtime_bus import PostgresRealtimeBus
from backend.services.realtime_service import RealtimeService

POSTGRES_URL = os.getenv("DEVFLOW_TEST_POSTGRES_URL", "")

pytestmark = pytest.mark.skipif(
    not POSTGRES_URL,
    reason="Set DEVFLOW_TEST_POSTGRES_URL to run the Postgres integration tests.",
)


@pytest.fixture
async def factory():
    engine = create_async_engine(POSTGRES_URL, pool_size=10, max_overflow=10)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def test_parallel_claims_never_duplicate_on_postgres(factory):
    tenant_id = str(uuid.uuid4())
    async with factory() as session:
        session.add(Tenant(id=tenant_id, name="postgres integration", slug=f"pg-{tenant_id[:8]}"))
        await session.commit()

    queue = DatabaseJobQueue(factory)
    total = 40
    for index in range(total):
        await queue.enqueue(
            QueueJob(
                execution_task_id=str(uuid.uuid4()),
                execution_id=str(uuid.uuid4()),
                task_id=str(uuid.uuid4()),
                tenant_id=tenant_id,
                workflow_id="workflow-shared",
                priority=index % 3,
            )
        )

    claimed: list[str] = []

    async def run_worker(worker_id: str) -> None:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if len(claimed) >= total:
                return
            job = await queue.dequeue(worker_id, timeout=0.25)
            if job is None:
                continue
            claimed.append(job.id)
            await queue.acknowledge(job.id)

    await asyncio.gather(*(run_worker(f"pg-worker-{index}") for index in range(4)))

    assert len(claimed) == total
    assert len(set(claimed)) == total
    stats = await queue.stats(tenant_id)
    assert stats["queued_jobs"] == 0
    assert stats["in_flight_jobs"] == 0
    assert stats["total_processed"] == total


class _RecordingSocket:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    async def accept(self) -> None:
        return None

    async def send_json(self, payload: dict) -> None:
        self.messages.append(payload)


def _plain_dsn() -> str:
    return POSTGRES_URL.replace("postgresql+asyncpg://", "postgresql://").replace(
        "postgresql+psycopg://", "postgresql://"
    )


async def test_realtime_bus_fans_out_across_replicas():
    channel = f"devflow_events_test_{uuid.uuid4().hex[:12]}"
    dsn = _plain_dsn()
    replica_a, replica_b = RealtimeService(), RealtimeService()
    bus_a = PostgresRealtimeBus(dsn, channel)
    bus_b = PostgresRealtimeBus(dsn, channel)
    try:
        await bus_a.start(replica_a.broadcast_local)
        await bus_b.start(replica_b.broadcast_local)
        replica_a.use_bus(bus_a)
        replica_b.use_bus(bus_b)

        socket_a, socket_b = _RecordingSocket(), _RecordingSocket()
        await replica_a.connect("exec-shared", socket_a)
        await replica_b.connect("exec-shared", socket_b)

        await replica_a.broadcast("exec-shared", {"status": "success"})

        deadline = time.monotonic() + 5
        while not socket_b.messages and time.monotonic() < deadline:
            await asyncio.sleep(0.05)

        assert socket_a.messages == [{"status": "success"}]
        assert socket_b.messages == [{"status": "success"}]
    finally:
        await bus_a.stop()
        await bus_b.stop()
