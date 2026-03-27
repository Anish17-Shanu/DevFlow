from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.core.time import utc_now
from backend.models.entities import Execution, ExecutionStatus, ExecutionTask, TaskState, Workflow
from backend.queue.job_queue import DatabaseJobQueue, QueueJob
from backend.services.log_service import LogService
from backend.services.realtime_service import RealtimeService


class ExecutionService:
    def __init__(self, queue: DatabaseJobQueue, realtime: RealtimeService):
        self.queue = queue
        self.realtime = realtime

    async def trigger_workflow(self, session, workflow_id: str) -> Execution:
        workflow = await session.scalar(
            select(Workflow).where(Workflow.id == workflow_id).options(selectinload(Workflow.tasks))
        )
        if not workflow:
            raise ValueError("Workflow not found.")

        execution = Execution(
            workflow_id=workflow.id,
            status=ExecutionStatus.running,
            started_at=utc_now(),
            updated_at=utc_now(),
        )
        session.add(execution)
        await session.flush()

        for task in workflow.tasks:
            session.add(
                ExecutionTask(
                    execution_id=execution.id,
                    task_id=task.id,
                    status=TaskState.pending,
                )
            )

        await LogService.write(session, execution.id, f"Execution created for workflow '{workflow.name}'.")
        await session.commit()

        await self.enqueue_ready_tasks(session, execution.id)
        await self.realtime.broadcast(execution.id, {"type": "execution.started", "executionId": execution.id})
        return execution

    async def enqueue_ready_tasks(self, session, execution_id: str) -> None:
        execution = await self._get_execution_with_tasks(session, execution_id)
        if not execution:
            raise ValueError("Execution not found.")

        workflow_tasks = {task.name: task for task in execution.workflow.tasks}
        execution_items = {item.task_id: item for item in execution.execution_tasks}
        changed = False

        for item in execution.execution_tasks:
            if item.status != TaskState.pending:
                continue

            dependency_names = item.task.dependencies or []
            dependency_states = [execution_items[workflow_tasks[name].id].status for name in dependency_names]

            if any(state == TaskState.failed for state in dependency_states):
                item.status = TaskState.failed
                item.finished_at = utc_now()
                item.error_message = "Blocked by failed dependency."
                execution.updated_at = utc_now()
                await LogService.write(
                    session,
                    execution.id,
                    f"Task '{item.task.name}' marked failed because a dependency failed.",
                    level="ERROR",
                    task_id=item.task_id,
                )
                changed = True
                continue

            if all(state == TaskState.success for state in dependency_states):
                config = item.task.config or {}
                delay_seconds = float(config.get("delay_seconds", 0))
                item.status = TaskState.queued
                execution.updated_at = utc_now()
                await self.queue.enqueue(
                    QueueJob(
                        execution_task_id=item.id,
                        execution_id=execution.id,
                        task_id=item.task_id,
                        priority=int(config.get("priority", 0)),
                        available_at=utc_now() + timedelta(seconds=delay_seconds),
                        retry_count=item.retries,
                    ),
                    session=session,
                )
                await LogService.write(
                    session,
                    execution.id,
                    f"Task '{item.task.name}' queued.",
                    task_id=item.task_id,
                )
                changed = True

        await self._refresh_execution_status(execution)
        await session.commit()

        if changed:
            await self.realtime.broadcast(execution.id, {"type": "execution.updated", "executionId": execution.id})

    async def execute_task(self, session, execution_task_id: str, worker_id: str, queue_job_id: str) -> None:
        item = await session.scalar(
            select(ExecutionTask)
            .where(ExecutionTask.id == execution_task_id)
            .options(
                selectinload(ExecutionTask.task),
                selectinload(ExecutionTask.execution).selectinload(Execution.workflow).selectinload(Workflow.tasks),
                selectinload(ExecutionTask.execution).selectinload(Execution.execution_tasks).selectinload(ExecutionTask.task),
            )
        )
        if not item:
            await self.queue.acknowledge(queue_job_id)
            return

        if item.status in {TaskState.success, TaskState.failed}:
            await self.queue.acknowledge(queue_job_id)
            return

        item.status = TaskState.running
        item.started_at = item.started_at or utc_now()
        item.worker_id = worker_id
        item.last_heartbeat_at = utc_now()
        item.execution.updated_at = utc_now()
        await LogService.write(
            session,
            item.execution_id,
            f"Worker {worker_id} started task '{item.task.name}'.",
            task_id=item.task_id,
        )
        await session.commit()
        await self.realtime.broadcast(
            item.execution_id,
            {"type": "task.running", "executionId": item.execution_id, "taskId": item.task_id},
        )

        config = item.task.config or {}
        duration_ms = int(config.get("duration_ms", 800))
        fail_first_n = int(config.get("fail_first_n", 0))
        max_retries = int(config.get("max_retries", 0))
        backoff_seconds = float(config.get("backoff_seconds", 1))

        await asyncio.sleep(duration_ms / 1000)

        should_fail = item.retries < fail_first_n
        if should_fail:
            item.retries += 1
            item.error_message = f"Simulated failure on attempt {item.retries}."

            if item.retries <= max_retries:
                item.status = TaskState.retrying
                item.execution.updated_at = utc_now()
                await LogService.write(
                    session,
                    item.execution_id,
                    f"Task '{item.task.name}' failed on attempt {item.retries}. Scheduling retry.",
                    level="WARNING",
                    task_id=item.task_id,
                )
                await self.queue.acknowledge(queue_job_id, session=session)
                item.status = TaskState.queued
                item.last_heartbeat_at = utc_now()
                item.execution.updated_at = utc_now()
                await self.queue.enqueue(
                    QueueJob(
                        execution_task_id=item.id,
                        execution_id=item.execution_id,
                        task_id=item.task_id,
                        priority=int(config.get("priority", 0)),
                        available_at=utc_now() + timedelta(seconds=backoff_seconds * (2 ** (item.retries - 1))),
                        retry_count=item.retries,
                    ),
                    session=session,
                )
                await session.commit()
                await self.realtime.broadcast(
                    item.execution_id,
                    {"type": "task.retrying", "executionId": item.execution_id, "taskId": item.task_id},
                )
                return

            item.status = TaskState.failed
            item.finished_at = utc_now()
            item.execution.updated_at = utc_now()
            await LogService.write(
                session,
                item.execution_id,
                f"Task '{item.task.name}' exhausted retries and failed.",
                level="ERROR",
                task_id=item.task_id,
            )
            await self.queue.acknowledge(queue_job_id, session=session)
            await self._fail_downstream(session, item)
            await self._finalize_execution(session, item.execution_id)
            await session.commit()
            await self.realtime.broadcast(
                item.execution_id,
                {"type": "task.failed", "executionId": item.execution_id, "taskId": item.task_id},
            )
            return

        item.status = TaskState.success
        item.finished_at = utc_now()
        item.error_message = None
        item.execution.updated_at = utc_now()
        await LogService.write(
            session,
            item.execution_id,
            f"Task '{item.task.name}' completed successfully.",
            task_id=item.task_id,
        )
        await self.queue.acknowledge(queue_job_id, session=session)
        await session.commit()

        await self.enqueue_ready_tasks(session, item.execution_id)
        await self._finalize_execution(session, item.execution_id)
        await session.commit()
        await self.realtime.broadcast(
            item.execution_id,
            {"type": "task.success", "executionId": item.execution_id, "taskId": item.task_id},
        )

    async def _get_execution_with_tasks(self, session, execution_id: str) -> Execution | None:
        return await session.scalar(
            select(Execution)
            .where(Execution.id == execution_id)
            .options(
                selectinload(Execution.workflow).selectinload(Workflow.tasks),
                selectinload(Execution.execution_tasks).selectinload(ExecutionTask.task),
            )
        )

    async def _fail_downstream(self, session, failed_item: ExecutionTask) -> None:
        execution = failed_item.execution
        workflow_tasks = {task.name: task for task in execution.workflow.tasks}
        execution_items = {item.task_id: item for item in execution.execution_tasks}

        changed = True
        while changed:
            changed = False
            for item in execution.execution_tasks:
                if item.status != TaskState.pending:
                    continue
                dependency_names = item.task.dependencies or []
                if any(execution_items[workflow_tasks[name].id].status == TaskState.failed for name in dependency_names):
                    item.status = TaskState.failed
                    item.finished_at = utc_now()
                    item.error_message = "Blocked by failed dependency."
                    execution.updated_at = utc_now()
                    await LogService.write(
                        session,
                        execution.id,
                        f"Task '{item.task.name}' blocked after upstream failure.",
                        level="ERROR",
                        task_id=item.task_id,
                    )
                    changed = True

    async def _refresh_execution_status(self, execution: Execution) -> None:
        states = {task.status for task in execution.execution_tasks}
        if states and all(state == TaskState.success for state in states):
            execution.status = ExecutionStatus.success
            execution.finished_at = execution.finished_at or utc_now()
            execution.updated_at = utc_now()
            return
        if any(state == TaskState.failed for state in states):
            execution.status = ExecutionStatus.failed
            execution.finished_at = execution.finished_at or utc_now()
            execution.updated_at = utc_now()
            return
        execution.status = ExecutionStatus.running
        execution.finished_at = None
        execution.updated_at = utc_now()

    async def _finalize_execution(self, session, execution_id: str) -> None:
        execution = await self._get_execution_with_tasks(session, execution_id)
        if execution:
            await self._refresh_execution_status(execution)
