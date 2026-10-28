from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from backend.core.config import settings
from backend.core.context import binding
from backend.core.metrics import EXECUTIONS, TASK_DURATION, TASK_WAIT, TASKS
from backend.core.security import ApiError
from backend.core.time import utc_now
from backend.handlers import HandlerError, registry
from backend.handlers.base import HandlerContext
from backend.models.entities import (
    Execution,
    ExecutionStatus,
    ExecutionTask,
    TaskState,
    Workflow,
    WorkflowRevision,
)
from backend.queue.job_queue import DatabaseJobQueue, DeadLetteredJob, QueueJob
from backend.services.log_service import LogService
from backend.services.outbox_service import OutboxService
from backend.services.realtime_service import RealtimeService
from backend.services.secret_service import SecretService

logger = logging.getLogger(__name__)

SATISFIED_STATES = {TaskState.success, TaskState.skipped}
ACTIVE_STATES = {TaskState.pending, TaskState.queued, TaskState.running, TaskState.retrying}
TERMINAL_EXECUTION_STATES = {ExecutionStatus.success, ExecutionStatus.failed, ExecutionStatus.cancelled}


class ExecutionService:
    def __init__(self, queue: DatabaseJobQueue, realtime: RealtimeService):
        self.queue = queue
        self.realtime = realtime
        self._inflight: dict[str, set[asyncio.Task]] = {}
        self._cancelling: set[str] = set()

    def cancel_inflight(self, execution_id: str) -> int:
        self._cancelling.add(execution_id)
        tasks = list(self._inflight.get(execution_id, ()))
        for task in tasks:
            task.cancel()
        return len(tasks)

    async def trigger_workflow(
        self,
        session,
        tenant_id: str,
        workflow_id: str,
        actor: str = "system",
        idempotency_key: str | None = None,
    ) -> Execution:
        if idempotency_key:
            existing = await session.scalar(
                select(Execution).where(
                    Execution.tenant_id == tenant_id,
                    Execution.idempotency_key == idempotency_key,
                )
            )
            if existing:
                return existing

        workflow = await session.scalar(
            select(Workflow)
            .where(Workflow.id == workflow_id, Workflow.tenant_id == tenant_id, Workflow.is_archived.is_(False))
            .options(selectinload(Workflow.tasks), selectinload(Workflow.revisions))
        )
        if not workflow:
            raise ApiError(404, "not_found", "Workflow not found.")

        active = await session.scalar(
            select(func.count())
            .select_from(Execution)
            .where(
                Execution.tenant_id == tenant_id,
                Execution.status.in_([ExecutionStatus.pending, ExecutionStatus.running]),
            )
        )
        if int(active or 0) >= settings.max_concurrent_executions_per_tenant:
            raise ApiError(
                429,
                "quota_exceeded",
                "Concurrent execution quota reached for this tenant.",
            )

        revision = max(workflow.revisions, key=lambda item: item.revision) if workflow.revisions else None
        if revision:
            document = revision.document
            revision_number = revision.revision
        else:
            document = self._document_from_tasks(workflow)
            revision_number = workflow.current_revision

        return await self._spawn(
            session,
            tenant_id=tenant_id,
            workflow=workflow,
            document=document,
            revision=revision,
            revision_number=revision_number,
            actor=actor,
            idempotency_key=idempotency_key,
        )

    async def retry_execution(self, session, tenant_id: str, execution_id: str, actor: str = "system") -> Execution:
        execution = await self._get_execution(session, tenant_id, execution_id)
        if execution.status not in TERMINAL_EXECUTION_STATES:
            raise ApiError(409, "conflict", "Only finished executions can be retried.")
        workflow = await session.scalar(
            select(Workflow).where(Workflow.id == execution.workflow_id).options(selectinload(Workflow.tasks))
        )
        if workflow is None:
            raise ApiError(404, "not_found", "Workflow no longer exists.")
        new_execution = await self._spawn(
            session,
            tenant_id=tenant_id,
            workflow=workflow,
            document=execution.snapshot,
            revision=None,
            revision_number=execution.revision,
            actor=actor,
            idempotency_key=None,
        )
        await LogService.write(
            session,
            new_execution.id,
            f"Execution retried from {execution.id}.",
        )
        await session.commit()
        return new_execution

    async def _spawn(
        self,
        session,
        tenant_id: str,
        workflow: Workflow,
        document: dict,
        revision: WorkflowRevision | None,
        revision_number: int,
        actor: str,
        idempotency_key: str | None,
    ) -> Execution:
        task_defs = {task.name: task for task in workflow.tasks}
        execution = Execution(
            tenant_id=tenant_id,
            workflow_id=workflow.id,
            workflow_revision_id=revision.id if revision else None,
            workflow_name=document.get("name") or workflow.name,
            revision=revision_number,
            snapshot=document,
            status=ExecutionStatus.running,
            idempotency_key=idempotency_key,
            triggered_by=actor,
            started_at=utc_now(),
            updated_at=utc_now(),
        )
        session.add(execution)
        await session.flush()

        for task in document.get("tasks", []):
            definition = task_defs.get(task["name"])
            session.add(
                ExecutionTask(
                    execution_id=execution.id,
                    task_id=definition.id if definition else None,
                    task_name=task["name"],
                    dependencies=list(task.get("dependencies") or []),
                    config=dict(task.get("config") or {}),
                    status=TaskState.pending,
                )
            )

        await LogService.write(session, execution.id, f"Execution created for workflow '{execution.workflow_name}'.")
        OutboxService.write(
            session,
            tenant_id,
            "execution.started",
            execution.id,
            {"executionId": execution.id, "workflowId": workflow.id, "status": "running"},
        )

        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            if idempotency_key:
                existing = await session.scalar(
                    select(Execution).where(
                        Execution.tenant_id == tenant_id,
                        Execution.idempotency_key == idempotency_key,
                    )
                )
                if existing:
                    return existing
            raise ApiError(409, "conflict", "Workflow execution conflict.") from None

        await self.enqueue_ready_tasks(session, execution.id)
        await self.realtime.broadcast(execution.id, {"type": "execution.started", "executionId": execution.id})
        return execution

    def _document_from_tasks(self, workflow: Workflow) -> dict:
        return {
            "name": workflow.name,
            "description": workflow.description,
            "revision": workflow.current_revision,
            "tasks": [
                {"name": task.name, "dependencies": task.dependencies or [], "config": task.config or {}}
                for task in workflow.tasks
            ],
        }

    async def enqueue_ready_tasks(self, session, execution_id: str) -> None:
        execution = await self._get_execution_with_tasks(session, execution_id)
        if not execution:
            raise ApiError(404, "not_found", "Execution not found.")

        if execution.cancellation_requested:
            for item in execution.execution_tasks:
                if item.status in ACTIVE_STATES:
                    item.status = TaskState.cancelled
                    item.finished_at = utc_now()
            execution.updated_at = utc_now()
            await self._refresh_execution_status(session, execution)
            await session.commit()
            return

        items_by_name = {item.task_name: item for item in execution.execution_tasks}
        changed = False

        for item in execution.execution_tasks:
            if item.status != TaskState.pending:
                continue
            dependency_items = [items_by_name.get(name) for name in item.dependencies]
            if any(dependency is None for dependency in dependency_items):
                item.status = TaskState.failed
                item.finished_at = utc_now()
                item.error_message = "Dependency definition is missing."
                await LogService.write(
                    session,
                    execution.id,
                    f"Task '{item.task_name}' failed because a dependency is missing.",
                    level="ERROR",
                    task_id=item.id,
                )
                changed = True
                continue

            if any(dependency.status == TaskState.failed for dependency in dependency_items):
                item.status = TaskState.failed
                item.finished_at = utc_now()
                item.error_message = "Blocked by failed dependency."
                execution.updated_at = utc_now()
                await LogService.write(
                    session,
                    execution.id,
                    f"Task '{item.task_name}' marked failed because a dependency failed.",
                    level="ERROR",
                    task_id=item.id,
                )
                changed = True
                continue

            if any(dependency.status == TaskState.cancelled for dependency in dependency_items):
                item.status = TaskState.cancelled
                item.finished_at = utc_now()
                item.error_message = "Blocked by cancelled dependency."
                changed = True
                continue

            if all(dependency.status in SATISFIED_STATES for dependency in dependency_items):
                config = item.config or {}
                delay_seconds = float(config.get("delay_seconds", 0))
                item.status = TaskState.queued
                item.last_heartbeat_at = utc_now()
                execution.updated_at = utc_now()
                await self.queue.enqueue(
                    QueueJob(
                        execution_task_id=item.id,
                        execution_id=execution.id,
                        task_id=item.task_id or "",
                        tenant_id=execution.tenant_id,
                        workflow_id=execution.workflow_id,
                        priority=int(config.get("priority", 0)),
                        available_at=utc_now() + timedelta(seconds=delay_seconds),
                        retry_count=item.retries,
                        max_attempts=settings.queue_poison_max_attempts,
                    ),
                    session=session,
                )
                await LogService.write(
                    session,
                    execution.id,
                    f"Task '{item.task_name}' queued.",
                    task_id=item.id,
                )
                changed = True

        await self._refresh_execution_status(session, execution)
        await session.commit()

        if changed:
            await self.realtime.broadcast(execution.id, {"type": "execution.updated", "executionId": execution.id})

    async def execute_task(
        self, session, execution_task_id: str, worker_id: str, queue_job_id: str, job: QueueJob
    ) -> None:
        item = await session.scalar(
            select(ExecutionTask)
            .where(ExecutionTask.id == execution_task_id)
            .options(selectinload(ExecutionTask.execution))
        )
        if not item:
            await self.queue.acknowledge(queue_job_id)
            return

        if item.status in {TaskState.success, TaskState.failed, TaskState.cancelled, TaskState.skipped}:
            await self.queue.acknowledge(queue_job_id)
            return

        execution = item.execution
        if execution.cancellation_requested:
            item.status = TaskState.cancelled
            item.finished_at = utc_now()
            await self.queue.acknowledge(queue_job_id, session=session)
            await self._refresh_execution_status(session, execution)
            await session.commit()
            return

        with binding(tenant_id=execution.tenant_id, execution_id=execution.id, task_id=item.id, worker_id=worker_id):
            await self._run_task(session, item, worker_id, queue_job_id, job)

    async def _run_task(self, session, item: ExecutionTask, worker_id: str, queue_job_id: str, job: QueueJob) -> None:
        execution = item.execution
        if job.enqueued_at is not None:
            wait_seconds = (utc_now() - job.enqueued_at).total_seconds()
            if wait_seconds >= 0:
                TASK_WAIT.observe(wait_seconds)

        item.status = TaskState.running
        item.started_at = item.started_at or utc_now()
        item.worker_id = worker_id
        item.last_heartbeat_at = utc_now()
        execution.updated_at = utc_now()
        await LogService.write(
            session,
            execution.id,
            f"Worker {worker_id} started task '{item.task_name}'.",
            task_id=item.id,
        )
        await session.commit()
        await self.realtime.broadcast(
            execution.id,
            {"type": "task.running", "executionId": execution.id, "taskId": item.task_id},
        )

        config = item.config or {}
        max_retries = int(config.get("max_retries", 0))
        fail_first_n = int(config.get("fail_first_n", 0))
        backoff_seconds = float(config.get("backoff_seconds", 1))
        timeout = min(float(config.get("timeout_seconds", 60)), float(settings.max_task_timeout_seconds))
        started_at = utc_now()

        handler_task: asyncio.Task | None = None
        try:
            if item.retries < fail_first_n:
                raise HandlerError(f"Simulated failure on attempt {item.retries + 1}.")
            handler = registry.get(str(config.get("type", "sleep")))
            context = HandlerContext(
                tenant_id=execution.tenant_id,
                execution_id=execution.id,
                task_name=item.task_name,
                config=config,
                secrets=SecretService(session),
                attempt=item.retries + 1,
            )
            handler_task = asyncio.create_task(handler(context))
            self._inflight.setdefault(execution.id, set()).add(handler_task)
            output = await asyncio.wait_for(handler_task, timeout=timeout)
        except TimeoutError:
            await self._handle_failure(
                session,
                item,
                queue_job_id,
                f"Task timed out after {timeout:.0f} seconds.",
                max_retries,
                backoff_seconds,
            )
            return
        except asyncio.CancelledError:
            if execution.id not in self._cancelling:
                raise
            self._cancelling.discard(execution.id)
            item.status = TaskState.cancelled
            item.finished_at = utc_now()
            item.last_heartbeat_at = utc_now()
            await LogService.write(
                session,
                execution.id,
                f"Task '{item.task_name}' cancelled while running.",
                level="WARNING",
                task_id=item.id,
            )
            await self.queue.acknowledge(queue_job_id, session=session)
            await self._finalize_execution(session, execution.id)
            await session.commit()
            TASKS.labels(status="cancelled").inc()
            await self.realtime.broadcast(
                execution.id,
                {"type": "task.cancelled", "executionId": execution.id, "taskId": item.task_id},
            )
            return
        except HandlerError as exc:
            await self._handle_failure(session, item, queue_job_id, str(exc), max_retries, backoff_seconds)
            return
        except Exception:
            logger.exception("Task '%s' crashed.", item.task_name)
            await self._handle_failure(
                session, item, queue_job_id, "Task handler raised an unexpected error.", max_retries, backoff_seconds
            )
            return
        finally:
            if handler_task is not None:
                bucket = self._inflight.get(execution.id)
                if bucket is not None:
                    bucket.discard(handler_task)
                    if not bucket:
                        self._inflight.pop(execution.id, None)

        if execution.cancellation_requested:
            item.status = TaskState.cancelled
            item.finished_at = utc_now()
            item.last_heartbeat_at = utc_now()
            await LogService.write(
                session, execution.id, f"Task '{item.task_name}' cancelled.", level="WARNING", task_id=item.id
            )
            await self.queue.acknowledge(queue_job_id, session=session)
            self._observe_task_duration(started_at, "cancelled")
            TASKS.labels(status="cancelled").inc()
            await self._finalize_execution(session, execution.id)
            await session.commit()
            await self.realtime.broadcast(
                execution.id,
                {"type": "task.cancelled", "executionId": execution.id, "taskId": item.task_id},
            )
            return

        item.status = TaskState.success
        item.finished_at = utc_now()
        item.error_message = None
        item.last_heartbeat_at = utc_now()
        execution.updated_at = utc_now()
        summary = self._summarize(output)
        await LogService.write(
            session,
            execution.id,
            f"Task '{item.task_name}' completed successfully.{summary}",
            task_id=item.id,
        )
        await self.queue.acknowledge(queue_job_id, session=session)
        TASKS.labels(status="success").inc()
        self._observe_task_duration(started_at, "success")
        await session.commit()

        await self.enqueue_ready_tasks(session, execution.id)
        await self._finalize_execution(session, execution.id)
        await session.commit()
        await self.realtime.broadcast(
            execution.id,
            {"type": "task.success", "executionId": execution.id, "taskId": item.task_id},
        )

    async def _handle_failure(
        self,
        session,
        item: ExecutionTask,
        queue_job_id: str,
        message: str,
        max_retries: int,
        backoff_seconds: float,
    ) -> None:
        execution = item.execution
        config = item.config or {}
        if config.get("allow_failure"):
            item.status = TaskState.success
            item.error_message = message[:2000]
            item.finished_at = utc_now()
            execution.updated_at = utc_now()
            await LogService.write(
                session,
                execution.id,
                f"Task '{item.task_name}' failed but allow_failure is set: {message}",
                level="WARNING",
                task_id=item.id,
            )
            await self.queue.acknowledge(queue_job_id, session=session)
            TASKS.labels(status="success").inc()
            await self.enqueue_ready_tasks(session, execution.id)
            await self._finalize_execution(session, execution.id)
            await session.commit()
            return

        item.retries += 1
        item.error_message = message[:2000]
        item.last_heartbeat_at = utc_now()
        execution.updated_at = utc_now()

        if item.retries <= max_retries:
            item.status = TaskState.retrying
            await LogService.write(
                session,
                execution.id,
                f"Task '{item.task_name}' failed on attempt {item.retries}: {message} Scheduling retry.",
                level="WARNING",
                task_id=item.id,
            )
            await self.queue.acknowledge(queue_job_id, session=session)
            item.status = TaskState.queued
            await self.queue.enqueue(
                QueueJob(
                    execution_task_id=item.id,
                    execution_id=execution.id,
                    task_id=item.task_id or "",
                    tenant_id=execution.tenant_id,
                    workflow_id=execution.workflow_id,
                    priority=int(config.get("priority", 0)),
                    available_at=utc_now() + timedelta(seconds=backoff_seconds * (2 ** (item.retries - 1))),
                    retry_count=item.retries,
                    max_attempts=settings.queue_poison_max_attempts,
                ),
                session=session,
            )
            await session.commit()
            await self.realtime.broadcast(
                execution.id,
                {"type": "task.retrying", "executionId": execution.id, "taskId": item.task_id},
            )
            return

        item.status = TaskState.failed
        item.finished_at = utc_now()
        await LogService.write(
            session,
            execution.id,
            f"Task '{item.task_name}' exhausted retries: {message}",
            level="ERROR",
            task_id=item.id,
        )
        TASKS.labels(status="failed").inc()
        await self.queue.acknowledge(queue_job_id, session=session)
        await self._fail_downstream(session, execution.id)
        await self._finalize_execution(session, execution.id)
        await session.commit()
        await self.realtime.broadcast(
            execution.id,
            {"type": "task.failed", "executionId": execution.id, "taskId": item.task_id},
        )

    async def handle_dead_letter(self, session, dead_letter: DeadLetteredJob) -> None:
        item = await session.get(ExecutionTask, dead_letter.execution_task_id)
        if item is None or item.status in {TaskState.success, TaskState.failed, TaskState.skipped}:
            return
        item.status = TaskState.failed
        item.finished_at = utc_now()
        item.error_message = dead_letter.error
        TASKS.labels(status="failed").inc()
        await LogService.write(
            session,
            item.execution_id,
            f"Task '{item.task_name}' dead-lettered after {dead_letter.attempts} attempts: {dead_letter.error}",
            level="ERROR",
            task_id=item.id,
        )
        await self._fail_downstream(session, item.execution_id)
        await self._finalize_execution(session, item.execution_id)
        await session.commit()
        await self.realtime.broadcast(
            item.execution_id,
            {"type": "task.failed", "executionId": item.execution_id, "taskId": item.task_id},
        )

    async def cancel_execution(self, session, tenant_id: str, execution_id: str, actor: str) -> Execution:
        execution = await self._get_execution(session, tenant_id, execution_id)
        if execution.status in TERMINAL_EXECUTION_STATES:
            return execution

        execution.cancellation_requested = True
        execution.updated_at = utc_now()
        for item in execution.execution_tasks:
            if item.status in {TaskState.pending, TaskState.queued, TaskState.retrying}:
                item.status = TaskState.cancelled
                item.finished_at = utc_now()
        await self.queue.cancel_execution_jobs(execution.id, session)
        await LogService.write(
            session,
            execution.id,
            f"Execution cancellation requested by {actor}.",
            level="WARNING",
        )
        await self._refresh_execution_status(session, execution)
        await session.commit()
        cancelled_inflight = self.cancel_inflight(execution.id)
        if cancelled_inflight:
            await asyncio.sleep(0.05)
            session.expire_all()
            execution = await self._get_execution(session, tenant_id, execution_id)
        else:
            self._cancelling.discard(execution.id)
        await self.realtime.broadcast(
            execution.id,
            {"type": "execution.updated", "executionId": execution.id, "status": execution.status.value},
        )
        return execution

    async def retry_task(
        self, session, tenant_id: str, execution_id: str, task_identifier: str, actor: str
    ) -> Execution:
        execution = await self._get_execution(session, tenant_id, execution_id)
        item = self._find_task(execution, task_identifier)
        if item.status in {TaskState.success, TaskState.skipped}:
            raise ApiError(409, "conflict", "Only failed, cancelled, or pending tasks can be retried.")
        if item.status == TaskState.running:
            raise ApiError(409, "conflict", "A running task cannot be retried.")

        reset_names = self._downstream_names(execution, item.task_name) | {item.task_name}
        for candidate in execution.execution_tasks:
            if candidate.task_name in reset_names and candidate.status in {
                TaskState.failed,
                TaskState.cancelled,
                TaskState.skipped,
                TaskState.pending,
            }:
                candidate.status = TaskState.pending
                candidate.retries = 0
                candidate.error_message = None
                candidate.started_at = None
                candidate.finished_at = None
                candidate.worker_id = None

        execution.cancellation_requested = False
        execution.status = ExecutionStatus.running
        execution.finished_at = None
        execution.updated_at = utc_now()
        await LogService.write(
            session,
            execution.id,
            f"Task '{item.task_name}' manually retried by {actor}.",
            task_id=item.id,
        )
        await session.commit()
        await self.enqueue_ready_tasks(session, execution.id)
        return execution

    async def skip_task(
        self, session, tenant_id: str, execution_id: str, task_identifier: str, actor: str
    ) -> Execution:
        execution = await self._get_execution(session, tenant_id, execution_id)
        item = self._find_task(execution, task_identifier)
        if item.status == TaskState.running:
            raise ApiError(409, "conflict", "A running task cannot be skipped.")
        if item.status in {TaskState.success, TaskState.skipped}:
            raise ApiError(409, "conflict", "Task is already complete.")

        item.status = TaskState.skipped
        item.finished_at = utc_now()
        item.error_message = None
        await self.queue.cancel_task_jobs(item.id, session)
        await LogService.write(
            session,
            execution.id,
            f"Task '{item.task_name}' skipped by {actor}.",
            level="WARNING",
            task_id=item.id,
        )
        await session.commit()
        await self.enqueue_ready_tasks(session, execution.id)
        await self._finalize_execution(session, execution.id)
        await session.commit()
        return execution

    def _find_task(self, execution: Execution, identifier: str) -> ExecutionTask:
        for item in execution.execution_tasks:
            if item.id == identifier or item.task_name == identifier:
                return item
        raise ApiError(404, "not_found", "Task not found in this execution.")

    def _downstream_names(self, execution: Execution, name: str) -> set[str]:
        children: dict[str, list[str]] = {}
        for item in execution.execution_tasks:
            for dependency in item.dependencies:
                children.setdefault(dependency, []).append(item.task_name)
        found: set[str] = set()
        stack = list(children.get(name, []))
        while stack:
            current = stack.pop()
            if current in found:
                continue
            found.add(current)
            stack.extend(children.get(current, []))
        return found

    async def _fail_downstream(self, session, execution_id: str) -> None:
        execution = await self._get_execution_with_tasks(session, execution_id)
        if not execution:
            return
        changed = True
        while changed:
            changed = False
            for item in execution.execution_tasks:
                if item.status != TaskState.pending:
                    continue
                dependency_states = [
                    candidate.status
                    for candidate in execution.execution_tasks
                    if candidate.task_name in item.dependencies
                ]
                if any(state == TaskState.failed for state in dependency_states):
                    item.status = TaskState.failed
                    item.finished_at = utc_now()
                    item.error_message = "Blocked by failed dependency."
                    execution.updated_at = utc_now()
                    await LogService.write(
                        session,
                        execution.id,
                        f"Task '{item.task_name}' blocked after upstream failure.",
                        level="ERROR",
                        task_id=item.id,
                    )
                    changed = True

    async def _refresh_execution_status(self, session, execution: Execution) -> None:
        previous = execution.status
        states = {task.status for task in execution.execution_tasks}
        if not states:
            execution.status = ExecutionStatus.pending
            return

        if any(state == TaskState.failed for state in states):
            execution.status = ExecutionStatus.failed
        elif execution.cancellation_requested and states <= {
            TaskState.success,
            TaskState.skipped,
            TaskState.cancelled,
            TaskState.failed,
        }:
            execution.status = ExecutionStatus.cancelled
        elif states <= SATISFIED_STATES:
            execution.status = ExecutionStatus.success
        elif TaskState.cancelled in states and not (states & {TaskState.pending, TaskState.queued, TaskState.running}):
            execution.status = ExecutionStatus.cancelled
        else:
            execution.status = ExecutionStatus.running
            execution.finished_at = None
            execution.updated_at = utc_now()
            return

        if execution.status in TERMINAL_EXECUTION_STATES:
            execution.finished_at = execution.finished_at or utc_now()
        execution.updated_at = utc_now()
        if previous != execution.status and execution.status in TERMINAL_EXECUTION_STATES:
            EXECUTIONS.labels(status=execution.status.value).inc()
            OutboxService.write(
                session,
                execution.tenant_id,
                f"execution.{execution.status.value}",
                execution.id,
                {
                    "executionId": execution.id,
                    "workflowId": execution.workflow_id,
                    "workflowName": execution.workflow_name,
                    "status": execution.status.value,
                },
            )

    async def finalize_execution(self, session, execution_id: str) -> None:
        await self._finalize_execution(session, execution_id)
        await session.commit()

    async def _finalize_execution(self, session, execution_id: str) -> None:
        execution = await self._get_execution_with_tasks(session, execution_id)
        if execution:
            await self._refresh_execution_status(session, execution)
            await self.realtime.broadcast(
                execution.id,
                {"type": "execution.updated", "executionId": execution.id, "status": execution.status.value},
            )

    async def _get_execution(self, session, tenant_id: str, execution_id: str) -> Execution:
        execution = await session.scalar(
            select(Execution)
            .where(Execution.id == execution_id, Execution.tenant_id == tenant_id)
            .options(selectinload(Execution.execution_tasks))
        )
        if not execution:
            raise ApiError(404, "not_found", "Execution not found.")
        return execution

    async def _get_execution_with_tasks(self, session, execution_id: str) -> Execution | None:
        return await session.scalar(
            select(Execution).where(Execution.id == execution_id).options(selectinload(Execution.execution_tasks))
        )

    @staticmethod
    def _summarize(output: dict | None) -> str:
        if not output:
            return ""
        rendered = ", ".join(f"{key}={value}" for key, value in output.items())
        return f" Output: {rendered[:500]}."

    @staticmethod
    def _observe_task_duration(started_at, status: str) -> None:
        elapsed = (utc_now() - started_at).total_seconds()
        TASK_DURATION.labels(status=status).observe(max(0.0, elapsed))
