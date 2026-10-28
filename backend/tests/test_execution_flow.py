import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.core.database import Base
from backend.models.entities import Execution, ExecutionStatus, ExecutionTask, TaskState
from backend.queue.job_queue import DatabaseJobQueue
from backend.schemas.workflow import WorkflowCreate
from backend.services.execution_service import ExecutionService
from backend.services.workflow_service import WorkflowService


class FakeRealtime:
    def __init__(self):
        self.events = []

    async def broadcast(self, execution_id, payload):
        self.events.append((execution_id, payload))


@pytest.fixture
async def flow_setup():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    try:
        yield session_factory
    finally:
        await engine.dispose()


async def _load_task_states(session, execution_id):
    result = await session.execute(select(ExecutionTask).where(ExecutionTask.execution_id == execution_id))
    return {item.task_id: item for item in result.scalars()}


async def test_execution_runs_ready_tasks_in_dependency_order(flow_setup):
    session_factory = flow_setup
    queue = DatabaseJobQueue(session_factory)
    service = ExecutionService(queue, FakeRealtime())

    async with session_factory() as session:
        workflow = await WorkflowService(session).create_workflow(
            WorkflowCreate(
                name="ordered-flow",
                tasks=[
                    {"name": "extract", "dependencies": [], "config": {"duration_ms": 100}},
                    {"name": "load", "dependencies": ["extract"], "config": {"duration_ms": 100}},
                ],
            )
        )
        execution = await service.trigger_workflow(session, workflow.id)

        first_job = await queue.dequeue(worker_id="worker-1", timeout=0.1)
        assert first_job is not None
        assert await queue.dequeue(worker_id="worker-1", timeout=0.05) is None

        await service.execute_task(session, first_job.execution_task_id, "worker-1", queue_job_id=first_job.id)
        second_job = await queue.dequeue(worker_id="worker-2", timeout=0.1)
        assert second_job is not None

        await service.execute_task(session, second_job.execution_task_id, "worker-2", queue_job_id=second_job.id)

        stored = await session.get(Execution, execution.id)
        assert stored.status == ExecutionStatus.success
        assert stored.finished_at is not None
        states = await _load_task_states(session, execution.id)
        assert {item.status for item in states.values()} == {TaskState.success}


async def test_failed_task_retries_with_backoff_and_then_succeeds(flow_setup):
    session_factory = flow_setup
    queue = DatabaseJobQueue(session_factory)
    service = ExecutionService(queue, FakeRealtime())

    async with session_factory() as session:
        workflow = await WorkflowService(session).create_workflow(
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
            )
        )
        execution = await service.trigger_workflow(session, workflow.id)

        first_job = await queue.dequeue(worker_id="worker-1", timeout=0.1)
        assert first_job is not None
        await service.execute_task(session, first_job.execution_task_id, "worker-1", queue_job_id=first_job.id)

        retry_job = await queue.dequeue(worker_id="worker-1", timeout=0.1)
        assert retry_job is not None
        assert retry_job.retry_count == 1
        await service.execute_task(session, retry_job.execution_task_id, "worker-1", queue_job_id=retry_job.id)

        stored = await session.get(Execution, execution.id)
        assert stored.status == ExecutionStatus.success
        states = await _load_task_states(session, execution.id)
        assert next(iter(states.values())).retries == 1
