from datetime import timedelta

from sqlalchemy import select

from backend.core.time import utc_now
from backend.models.entities import (
    Execution,
    ExecutionLog,
    ExecutionStatus,
    QueueJobRecord,
    QueueJobState,
    Tenant,
    WorkerRecord,
)
from backend.services.retention_service import RetentionService

TENANT = "retention-tenant"


async def test_retention_removes_expired_records_and_keeps_active_work(session_factory, monkeypatch):
    from backend.core.config import settings

    for name in (
        "log_retention_days",
        "execution_retention_days",
        "queue_retention_days",
        "worker_retention_days",
    ):
        monkeypatch.setattr(settings, name, 1)

    old = utc_now() - timedelta(days=2)
    async with session_factory() as session:
        session.add(Tenant(id=TENANT, name="Retention tenant", slug="retention"))
        session.add_all(
            [
                Execution(
                    id="old-exec",
                    tenant_id=TENANT,
                    workflow_id="wf",
                    workflow_name="old",
                    snapshot={},
                    status=ExecutionStatus.success,
                    created_at=old,
                    finished_at=old,
                ),
                Execution(
                    id="active-exec",
                    tenant_id=TENANT,
                    workflow_id="wf",
                    workflow_name="active",
                    snapshot={},
                    status=ExecutionStatus.running,
                    created_at=old,
                ),
                ExecutionLog(execution_id="old-exec", message="expired", created_at=old),
                ExecutionLog(execution_id="active-exec", message="still running", created_at=utc_now()),
                QueueJobRecord(
                    tenant_id=TENANT,
                    workflow_id="wf",
                    execution_task_id="task-old",
                    execution_id="old-exec",
                    task_id="task-old",
                    state=QueueJobState.completed,
                    completed_at=old,
                    created_at=old,
                ),
                WorkerRecord(worker_id="old-worker", is_active=False, last_seen_at=old),
            ]
        )
        await session.commit()

    deleted = await RetentionService(session_factory).run_once()

    assert deleted["executions"] == 1
    assert deleted["queue_jobs"] == 1
    assert deleted["workers"] == 1
    assert deleted["logs"] == 1

    async with session_factory() as session:
        remaining = list((await session.execute(select(Execution.id))).scalars())
        logs = list((await session.execute(select(ExecutionLog.execution_id))).scalars())
        workers = list((await session.execute(select(WorkerRecord.worker_id))).scalars())

    assert remaining == ["active-exec"]
    assert logs == ["active-exec"]
    assert workers == []
