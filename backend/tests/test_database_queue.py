from datetime import timedelta

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.core.database import Base
from backend.core.time import utc_now
from backend.models.entities import QueueJobRecord, QueueJobState
from backend.queue.job_queue import DatabaseJobQueue, QueueJob


@pytest.fixture
async def queue_setup():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    try:
        yield DatabaseJobQueue(session_factory), session_factory
    finally:
        await engine.dispose()


async def test_database_queue_enqueue_dequeue_ack(queue_setup):
    queue, _session_factory = queue_setup
    job = QueueJob(
        execution_task_id="execution-task-1",
        execution_id="execution-1",
        task_id="task-1",
        priority=5,
    )

    await queue.enqueue(job)
    leased = await queue.dequeue(worker_id="worker-1", timeout=0.1)

    assert leased is not None
    assert leased.id == job.id
    stats = await queue.stats()
    assert stats["in_flight_jobs"] == 1

    await queue.acknowledge(job.id)
    stats = await queue.stats()
    assert stats["total_processed"] == 1
    assert stats["in_flight_jobs"] == 0


async def test_database_queue_requeues_expired_leases(queue_setup):
    queue, session_factory = queue_setup
    job = QueueJob(
        execution_task_id="execution-task-2",
        execution_id="execution-2",
        task_id="task-2",
        priority=1,
    )

    await queue.enqueue(job)
    leased = await queue.dequeue(worker_id="worker-1", timeout=0.1)
    assert leased is not None

    async with session_factory() as session:
        await session.execute(
            update(QueueJobRecord)
            .where(QueueJobRecord.id == job.id)
            .values(
                state=QueueJobState.leased,
                leased_by="worker-1",
                lease_expires_at=utc_now() - timedelta(seconds=1),
            )
        )
        await session.commit()

    requeued = await queue.requeue_stale_jobs()
    assert requeued == 1

    reclaimed = await queue.dequeue(worker_id="worker-2", timeout=0.1)
    assert reclaimed is not None
    assert reclaimed.id == job.id
