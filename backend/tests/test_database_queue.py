from datetime import timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import update

from backend.core.time import utc_now
from backend.models.entities import QueueJobRecord, QueueJobState
from backend.queue.job_queue import DatabaseJobQueue, QueueJob

TENANT = "tenant-a"
OTHER_TENANT = "tenant-b"


async def _expire_lease(session_factory, job_id: str, attempts: int | None = None) -> None:
    values = {
        "state": QueueJobState.leased,
        "leased_by": "worker-1",
        "lease_expires_at": utc_now() - timedelta(seconds=1),
    }
    if attempts is not None:
        values["attempts"] = attempts
    async with session_factory() as session:
        await session.execute(update(QueueJobRecord).where(QueueJobRecord.id == job_id).values(**values))
        await session.commit()


async def test_enqueue_requires_tenant():
    queue = DatabaseJobQueue(SimpleNamespace(kw={}))
    with pytest.raises(ValueError):
        await queue.enqueue(QueueJob(execution_task_id="task"))


async def test_queue_enqueue_dequeue_ack(session_factory):
    queue = DatabaseJobQueue(session_factory)
    job = QueueJob(
        execution_task_id="execution-task-1",
        execution_id="execution-1",
        task_id="task-1",
        tenant_id=TENANT,
        priority=5,
    )

    await queue.enqueue(job)
    leased = await queue.dequeue(worker_id="worker-1", timeout=0.1)

    assert leased is not None
    assert leased.id == job.id
    assert leased.tenant_id == TENANT
    stats = await queue.stats()
    assert stats["in_flight_jobs"] == 1

    assert await queue.renew_lease(job.id, "worker-1") is True
    assert await queue.renew_lease(job.id, "other-worker") is False

    await queue.acknowledge(job.id)
    stats = await queue.stats()
    assert stats["total_processed"] == 1
    assert stats["in_flight_jobs"] == 0


async def test_queue_tenant_scoped_stats_and_dead_letters(session_factory):
    queue = DatabaseJobQueue(session_factory)
    await queue.enqueue(QueueJob(execution_task_id="a", tenant_id=TENANT))
    await queue.enqueue(QueueJob(execution_task_id="b", tenant_id=OTHER_TENANT))

    assert (await queue.stats(TENANT))["total_enqueued"] == 1
    assert (await queue.stats(OTHER_TENANT))["total_enqueued"] == 1
    assert (await queue.stats())["total_enqueued"] == 2


async def test_queue_respects_priority_and_delay(session_factory):
    queue = DatabaseJobQueue(session_factory)
    await queue.enqueue(QueueJob(execution_task_id="low", tenant_id=TENANT, priority=1))
    await queue.enqueue(QueueJob(execution_task_id="high", tenant_id=TENANT, priority=9))
    delayed = QueueJob(
        execution_task_id="delayed",
        tenant_id=TENANT,
        priority=100,
        available_at=utc_now() + timedelta(minutes=5),
    )
    await queue.enqueue(delayed)

    stats = await queue.stats()
    assert stats["delayed_jobs"] == 1
    assert stats["queued_jobs"] == 2

    first = await queue.dequeue(worker_id="worker-1", timeout=0.1)
    second = await queue.dequeue(worker_id="worker-2", timeout=0.1)
    assert first.execution_task_id == "high"
    assert second.execution_task_id == "low"
    assert await queue.dequeue(worker_id="worker-3", timeout=0.05) is None


async def test_queue_requeues_expired_leases(session_factory):
    queue = DatabaseJobQueue(session_factory)
    job = QueueJob(execution_task_id="execution-task-2", execution_id="execution-2", tenant_id=TENANT)

    await queue.enqueue(job)
    leased = await queue.dequeue(worker_id="worker-1", timeout=0.1)
    assert leased is not None
    await _expire_lease(session_factory, job.id)

    dead_letters = await queue.requeue_stale_jobs()
    assert dead_letters == []
    assert await queue.stale_lease_count() == 0

    reclaimed = await queue.dequeue(worker_id="worker-2", timeout=0.1)
    assert reclaimed is not None
    assert reclaimed.id == job.id
    assert reclaimed.attempts == 2


async def test_queue_dead_letters_after_max_attempts(session_factory):
    queue = DatabaseJobQueue(session_factory)
    job = QueueJob(execution_task_id="execution-task-3", execution_id="execution-3", tenant_id=TENANT)

    await queue.enqueue(job)
    await queue.dequeue(worker_id="worker-1", timeout=0.1)
    await _expire_lease(session_factory, job.id, attempts=5)

    dead_letters = await queue.requeue_stale_jobs()
    assert len(dead_letters) == 1
    assert dead_letters[0].id == job.id
    assert dead_letters[0].tenant_id == TENANT
    assert await queue.dead_letter_count() == 1

    listed = await queue.list_dead_letters(TENANT)
    assert [item.id for item in listed] == [job.id]
    assert await queue.list_dead_letters(OTHER_TENANT) == []

    replayed = await queue.replay_dead_letter(TENANT, job.id)
    assert replayed is not None
    assert replayed.state == QueueJobState.queued
    assert replayed.attempts == 0
    assert await queue.dead_letter_count() == 0


async def test_queue_workflow_concurrency_limit(session_factory, monkeypatch):
    from backend.core.config import settings

    monkeypatch.setattr(settings, "max_concurrent_tasks_per_workflow", 1)
    queue = DatabaseJobQueue(session_factory)
    await queue.enqueue(QueueJob(execution_task_id="one", tenant_id=TENANT, workflow_id="wf-1"))
    await queue.enqueue(QueueJob(execution_task_id="two", tenant_id=TENANT, workflow_id="wf-1"))

    assert await queue.dequeue(worker_id="worker-1", timeout=0.1) is not None
    assert await queue.dequeue(worker_id="worker-2", timeout=0.05) is None
