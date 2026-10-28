import hashlib
import hmac
import json
from datetime import timedelta

import pytest
from sqlalchemy import select, update

from backend.core.security import ApiError
from backend.core.time import utc_now
from backend.models.entities import (
    Execution,
    ExecutionStatus,
    ExecutionTask,
    OutboxEvent,
    QueueJobRecord,
    QueueJobState,
    TaskState,
    Tenant,
    WebhookDelivery,
    WebhookEndpoint,
    WorkflowSchedule,
)
from backend.queue.job_queue import DatabaseJobQueue
from backend.schemas.ops import SecretCreate
from backend.schemas.workflow import WorkflowCreate
from backend.services.execution_service import ExecutionService
from backend.services.outbox_notifier_service import OutboxNotifierService
from backend.services.outbox_service import OutboxService
from backend.services.realtime_service import RealtimeService
from backend.services.scheduler_service import SchedulerService
from backend.services.secret_service import SecretService
from backend.services.watchdog_service import WatchdogService
from backend.services.webhook_service import WebhookDispatcherService
from backend.services.workflow_service import WorkflowService

TENANT = "service-tenant"


async def _ensure_tenant(session_factory):
    async with session_factory() as session:
        session.add(Tenant(id=TENANT, name="Service tenant", slug="service-tenant"))
        await session.commit()


class RecordingRealtime(RealtimeService):
    def __init__(self) -> None:
        super().__init__()
        self.events: list[tuple[str, dict]] = []

    async def broadcast(self, execution_id: str, payload: dict) -> None:
        self.events.append((execution_id, payload))


async def test_secrets_are_encrypted_and_rendered(session_factory):
    await _ensure_tenant(session_factory)
    async with session_factory() as session:
        service = SecretService(session)
        record = await service.create(TENANT, SecretCreate(name="api-token", value="plain-value"))

        assert record.ciphertext != "plain-value"
        assert await service.resolve(TENANT, "api-token") == "plain-value"
        rendered = await service.render_template(TENANT, "Bearer {{secret:api-token}}")
        assert rendered == "Bearer plain-value"

        with pytest.raises(ApiError) as missing:
            await service.resolve(TENANT, "unknown")
        assert missing.value.status_code == 400

        await service.create(TENANT, SecretCreate(name="api-token", value="rotated-value"))
        assert await service.resolve(TENANT, "api-token") == "rotated-value"

        await service.delete(TENANT, "api-token")
        assert await service.list(TENANT) == []


class _FakeResponse:
    status_code = 204


class _FakeAsyncClient:
    calls: list[dict] = []

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, content=None, headers=None):
        self.calls.append({"url": url, "content": content, "headers": headers})
        return _FakeResponse()


async def test_webhook_dispatch_signs_payload(session_factory, monkeypatch):
    await _ensure_tenant(session_factory)
    secret = "0123456789abcdef0123456789abcdef"
    async with session_factory() as session:
        endpoint = WebhookEndpoint(
            tenant_id=TENANT,
            url="https://example.com/hook",
            secret=secret,
            events=["execution.succeeded"],
        )
        session.add(endpoint)
        await session.commit()
        await session.refresh(endpoint)
        delivery = WebhookDelivery(
            tenant_id=TENANT,
            endpoint_id=endpoint.id,
            event_type="execution.succeeded",
            payload={"executionId": "exec-1", "status": "success"},
        )
        session.add(delivery)
        await session.commit()
        delivery_id = delivery.id

    _FakeAsyncClient.calls = []
    monkeypatch.setattr("backend.services.webhook_service.httpx.AsyncClient", _FakeAsyncClient)

    await WebhookDispatcherService(session_factory).dispatch_once()

    async with session_factory() as session:
        stored = await session.get(WebhookDelivery, delivery_id)
        assert stored.status == "delivered"
        assert stored.attempts == 1
        assert stored.delivered_at is not None

    assert len(_FakeAsyncClient.calls) == 1
    call = _FakeAsyncClient.calls[0]
    expected = hmac.new(secret.encode(), call["content"].encode(), hashlib.sha256).hexdigest()
    assert call["headers"]["X-DevFlow-Signature"] == f"sha256={expected}"
    assert call["headers"]["X-DevFlow-Event"] == "execution.succeeded"
    assert json.loads(call["content"])["executionId"] == "exec-1"


async def test_outbox_notifier_fans_out_events_and_deliveries(session_factory):
    await _ensure_tenant(session_factory)
    realtime = RecordingRealtime()
    async with session_factory() as session:
        endpoint = WebhookEndpoint(
            tenant_id=TENANT,
            url="https://example.com/hook",
            secret="0123456789abcdef0123456789abcdef",
            events=["execution.succeeded"],
        )
        session.add(endpoint)
        OutboxService.write(
            session,
            TENANT,
            "execution.succeeded",
            "exec-42",
            {"executionId": "exec-42", "status": "success"},
        )
        OutboxService.write(session, TENANT, "execution.started", "exec-42", {"status": "running"})
        await session.commit()

    await OutboxNotifierService(session_factory, realtime).poll_once()

    async with session_factory() as session:
        events = list((await session.execute(select(OutboxEvent))).scalars())
        deliveries = list((await session.execute(select(WebhookDelivery))).scalars())

    assert all(event.processed_at is not None for event in events)
    assert len(deliveries) == 1
    assert deliveries[0].event_type == "execution.succeeded"
    assert [payload["type"] for _, payload in realtime.events] == ["execution.succeeded", "execution.started"]

    await OutboxNotifierService(session_factory, realtime).poll_once()
    async with session_factory() as session:
        assert len(list((await session.execute(select(WebhookDelivery))).scalars())) == 1


async def test_scheduler_triggers_due_schedules_once(session_factory):
    await _ensure_tenant(session_factory)
    queue = DatabaseJobQueue(session_factory)
    execution_service = ExecutionService(queue, RecordingRealtime())
    scheduler = SchedulerService(session_factory, execution_service)

    async with session_factory() as session:
        workflow = await WorkflowService(session).create_workflow(
            TENANT, WorkflowCreate(name="scheduled", tasks=[{"name": "only"}])
        )
        schedule = WorkflowSchedule(
            tenant_id=TENANT,
            workflow_id=workflow.id,
            interval_seconds=60,
            next_run_at=utc_now() - timedelta(seconds=5),
        )
        session.add(schedule)
        await session.commit()
        schedule_id = schedule.id

    assert await scheduler.run_once() == 1
    assert await scheduler.run_once() == 0

    async with session_factory() as session:
        executions = list((await session.execute(select(Execution))).scalars())
        stored = await session.get(WorkflowSchedule, schedule_id)
        assert len(executions) == 1
        assert executions[0].triggered_by == "scheduler"
        assert stored.last_run_at is not None
        assert stored.next_run_at > utc_now()


async def test_scheduler_disables_archived_workflow_schedules(session_factory):
    await _ensure_tenant(session_factory)
    queue = DatabaseJobQueue(session_factory)
    scheduler = SchedulerService(session_factory, ExecutionService(queue, RecordingRealtime()))

    async with session_factory() as session:
        workflow = await WorkflowService(session).create_workflow(
            TENANT, WorkflowCreate(name="archived-schedule", tasks=[{"name": "only"}])
        )
        schedule = WorkflowSchedule(
            tenant_id=TENANT,
            workflow_id=workflow.id,
            interval_seconds=60,
            next_run_at=utc_now() - timedelta(seconds=5),
        )
        session.add(schedule)
        workflow.is_archived = True
        await session.commit()
        schedule_id = schedule.id

    assert await scheduler.run_once() == 0

    async with session_factory() as session:
        stored = await session.get(WorkflowSchedule, schedule_id)
        assert stored.is_enabled is False


async def test_watchdog_dead_letters_lost_jobs(session_factory):
    await _ensure_tenant(session_factory)
    queue = DatabaseJobQueue(session_factory)
    execution_service = ExecutionService(queue, RecordingRealtime())
    watchdog = WatchdogService(session_factory, queue, execution_service)

    async with session_factory() as session:
        workflow = await WorkflowService(session).create_workflow(
            TENANT, WorkflowCreate(name="watchdog-flow", tasks=[{"name": "only"}])
        )
        execution = await execution_service.trigger_workflow(session, TENANT, workflow.id)

    job = await queue.dequeue(worker_id="lost-worker", timeout=0.1)
    assert job is not None

    async with session_factory() as session:
        await session.execute(
            update(QueueJobRecord)
            .where(QueueJobRecord.id == job.id)
            .values(
                attempts=5,
                lease_expires_at=utc_now() - timedelta(seconds=1),
                state=QueueJobState.leased,
            )
        )
        await session.commit()

    await watchdog.run_once()

    async with session_factory() as session:
        stored_execution = await session.get(Execution, execution.id)
        task = await session.scalar(select(ExecutionTask).where(ExecutionTask.execution_id == execution.id))
        stored_job = await session.get(QueueJobRecord, job.id)

    assert stored_execution.status == ExecutionStatus.failed
    assert task.status == TaskState.failed
    assert stored_job.dead_lettered is True


async def test_outbox_notifier_loop_survives_poll_failures(session_factory, monkeypatch):
    import asyncio

    from backend.core.config import settings

    monkeypatch.setattr(settings, "realtime_poll_interval_ms", 250)
    notifier = OutboxNotifierService(session_factory, RecordingRealtime())
    calls: list[int] = []

    async def flaky_poll() -> None:
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("database temporarily unavailable")
        notifier._running = False

    monkeypatch.setattr(notifier, "poll_once", flaky_poll)
    notifier._running = True

    await asyncio.wait_for(notifier._run(), timeout=3)

    assert calls == [1, 1]


async def test_worker_shutdown_drains_inflight_task(session_factory):
    import asyncio

    from backend.workers.runtime import WorkerManager

    await _ensure_tenant(session_factory)
    queue = DatabaseJobQueue(session_factory)
    execution_service = ExecutionService(queue, RecordingRealtime())
    manager = WorkerManager(queue, execution_service, session_factory)

    async with session_factory() as session:
        workflow = await WorkflowService(session).create_workflow(
            TENANT,
            WorkflowCreate(
                name="drain-flow",
                tasks=[{"name": "slow", "config": {"type": "sleep", "duration_ms": 250}}],
            ),
        )
        execution = await execution_service.trigger_workflow(session, TENANT, workflow.id)

    await manager.start(worker_count=1)
    await asyncio.sleep(0.1)
    await manager.stop()

    async with session_factory() as session:
        stored = await session.get(Execution, execution.id)

    assert stored.status == ExecutionStatus.success
    assert manager._snapshots[next(iter(manager._snapshots))].state == "stopped"
