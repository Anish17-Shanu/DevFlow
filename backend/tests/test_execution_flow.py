import asyncio

from sqlalchemy import select

from backend.models.entities import Execution, ExecutionStatus, ExecutionTask, TaskState
from backend.queue.job_queue import DatabaseJobQueue
from backend.schemas.workflow import WorkflowCreate
from backend.services.execution_service import ExecutionService
from backend.services.realtime_service import RealtimeService
from backend.services.workflow_service import WorkflowService

TENANT = "tenant-flow"


class RecordingRealtime(RealtimeService):
    def __init__(self) -> None:
        super().__init__()
        self.events: list[tuple[str, dict]] = []

    async def broadcast(self, execution_id: str, payload: dict) -> None:
        self.events.append((execution_id, payload))


async def _load_tasks(session, execution_id):
    result = await session.execute(select(ExecutionTask).where(ExecutionTask.execution_id == execution_id))
    return {item.task_name: item for item in result.scalars()}


async def _run_all_jobs(service, queue, session, limit: int = 20):
    for index in range(limit):
        job = await queue.dequeue(worker_id=f"worker-{index}", timeout=0)
        if job is None:
            return
        await service.execute_task(session, job.execution_task_id, f"worker-{index}", queue_job_id=job.id, job=job)


async def test_execution_runs_ready_tasks_in_dependency_order(session_factory):
    queue = DatabaseJobQueue(session_factory)
    realtime = RecordingRealtime()
    service = ExecutionService(queue, realtime)

    async with session_factory() as session:
        workflow = await WorkflowService(session).create_workflow(
            TENANT,
            WorkflowCreate(
                name="ordered-flow",
                tasks=[
                    {"name": "extract", "dependencies": [], "config": {"duration_ms": 100}},
                    {"name": "load", "dependencies": ["extract"], "config": {"duration_ms": 100}},
                ],
            ),
        )
        execution = await service.trigger_workflow(session, TENANT, workflow.id)

        first_job = await queue.dequeue(worker_id="worker-1", timeout=0.1)
        assert first_job is not None
        assert await queue.dequeue(worker_id="worker-1", timeout=0.05) is None

        await service.execute_task(
            session, first_job.execution_task_id, "worker-1", queue_job_id=first_job.id, job=first_job
        )
        second_job = await queue.dequeue(worker_id="worker-2", timeout=0.1)
        assert second_job is not None
        await service.execute_task(
            session, second_job.execution_task_id, "worker-2", queue_job_id=second_job.id, job=second_job
        )

        stored = await session.get(Execution, execution.id)
        assert stored.status == ExecutionStatus.success
        assert stored.finished_at is not None
        states = await _load_tasks(session, execution.id)
        assert {item.status for item in states.values()} == {TaskState.success}
        assert any(event[1]["type"] == "execution.updated" for event in realtime.events)


async def test_failed_task_retries_with_backoff_and_then_succeeds(session_factory):
    queue = DatabaseJobQueue(session_factory)
    service = ExecutionService(queue, RecordingRealtime())

    async with session_factory() as session:
        workflow = await WorkflowService(session).create_workflow(
            TENANT,
            WorkflowCreate(
                name="retry-flow",
                tasks=[
                    {
                        "name": "flaky",
                        "dependencies": [],
                        "config": {
                            "duration_ms": 100,
                            "fail_first_n": 1,
                            "max_retries": 1,
                            "backoff_seconds": 0,
                        },
                    }
                ],
            ),
        )
        execution = await service.trigger_workflow(session, TENANT, workflow.id)

        first_job = await queue.dequeue(worker_id="worker-1", timeout=0.1)
        assert first_job is not None
        await service.execute_task(
            session, first_job.execution_task_id, "worker-1", queue_job_id=first_job.id, job=first_job
        )
        states = await _load_tasks(session, execution.id)
        assert states["flaky"].status == TaskState.queued
        assert states["flaky"].retries == 1

        retry_job = await queue.dequeue(worker_id="worker-1", timeout=0.1)
        assert retry_job is not None
        assert retry_job.retry_count == 1
        await service.execute_task(
            session, retry_job.execution_task_id, "worker-1", queue_job_id=retry_job.id, job=retry_job
        )

        stored = await session.get(Execution, execution.id)
        assert stored.status == ExecutionStatus.success
        states = await _load_tasks(session, execution.id)
        assert states["flaky"].retries == 1
        assert states["flaky"].status == TaskState.success


async def test_failed_task_fails_downstream_tasks(session_factory):
    queue = DatabaseJobQueue(session_factory)
    service = ExecutionService(queue, RecordingRealtime())

    async with session_factory() as session:
        workflow = await WorkflowService(session).create_workflow(
            TENANT,
            WorkflowCreate(
                name="failure-flow",
                tasks=[
                    {"name": "root", "config": {"fail_first_n": 1, "max_retries": 0}},
                    {"name": "child", "dependencies": ["root"], "config": {}},
                ],
            ),
        )
        execution = await service.trigger_workflow(session, TENANT, workflow.id)
        await _run_all_jobs(service, queue, session)

        stored = await session.get(Execution, execution.id)
        assert stored.status == ExecutionStatus.failed
        states = await _load_tasks(session, execution.id)
        assert states["root"].status == TaskState.failed
        assert states["child"].status == TaskState.failed


async def test_idempotency_key_reuses_execution(session_factory):
    queue = DatabaseJobQueue(session_factory)
    service = ExecutionService(queue, RecordingRealtime())

    async with session_factory() as session:
        workflow = await WorkflowService(session).create_workflow(
            TENANT, WorkflowCreate(name="idempotent-flow", tasks=[{"name": "only"}])
        )
        first = await service.trigger_workflow(session, TENANT, workflow.id, idempotency_key="abc-123")
        second = await service.trigger_workflow(session, TENANT, workflow.id, idempotency_key="abc-123")
        third = await service.trigger_workflow(session, TENANT, workflow.id, idempotency_key="abc-456")

        assert first.id == second.id
        assert third.id != first.id
        count = len((await session.execute(select(Execution))).scalars().all())
        assert count == 2


async def test_cancel_running_execution_stops_handler(session_factory):
    queue = DatabaseJobQueue(session_factory)
    service = ExecutionService(queue, RecordingRealtime())

    async with session_factory() as setup_session:
        workflow = await WorkflowService(setup_session).create_workflow(
            TENANT,
            WorkflowCreate(
                name="slow-flow",
                tasks=[{"name": "slow", "config": {"duration_ms": 30000, "timeout_seconds": 60}}],
            ),
        )
        execution = await service.trigger_workflow(setup_session, TENANT, workflow.id)

    job = await queue.dequeue(worker_id="worker-1", timeout=0.1)
    assert job is not None

    async def run_task():
        async with session_factory() as task_session:
            await service.execute_task(task_session, job.execution_task_id, "worker-1", queue_job_id=job.id, job=job)

    runner = asyncio.create_task(run_task())
    await asyncio.sleep(0.2)
    assert not runner.done()

    async with session_factory() as cancel_session:
        cancelled = await service.cancel_execution(cancel_session, TENANT, execution.id, actor="tester")

    await asyncio.wait_for(runner, timeout=5)
    assert cancelled.status == ExecutionStatus.cancelled

    async with session_factory() as session:
        stored = await session.get(Execution, execution.id)
        assert stored.status == ExecutionStatus.cancelled
        tasks = await _load_tasks(session, execution.id)
        assert tasks["slow"].status == TaskState.cancelled
