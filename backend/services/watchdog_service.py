from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.core.config import settings
from backend.core.time import utc_now
from backend.models.entities import Execution, ExecutionStatus, ExecutionTask, TaskState
from backend.queue.job_queue import DatabaseJobQueue, DeadLetteredJob
from backend.services.execution_service import ACTIVE_STATES, ExecutionService

logger = logging.getLogger(__name__)


class WatchdogService:
    def __init__(
        self,
        session_factory: async_sessionmaker,
        queue: DatabaseJobQueue,
        execution_service: ExecutionService,
    ) -> None:
        self._session_factory = session_factory
        self._queue = queue
        self._execution_service = execution_service
        self._task: asyncio.Task | None = None
        self._running = False

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._running = False
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    async def _run(self) -> None:
        while self._running:
            try:
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Watchdog iteration failed; retrying.")
            await asyncio.sleep(settings.watchdog_interval_seconds)

    async def run_once(self) -> None:
        dead_letters = await self._queue.requeue_stale_jobs()
        for dead_letter in dead_letters:
            async with self._session_factory() as session:
                await self._execution_service.handle_dead_letter(session, dead_letter)
        self._queue.drain_dead_letters()

        await self._enforce_cancellations()
        await self._reap_hung_tasks()
        await self._finalize_orphaned_executions()

    async def _enforce_cancellations(self) -> None:
        async with self._session_factory() as session:
            result = await session.execute(
                select(Execution.id).where(
                    Execution.cancellation_requested.is_(True),
                    Execution.status == ExecutionStatus.running,
                )
            )
            execution_ids = list(result.scalars())
        for execution_id in execution_ids:
            self._execution_service.cancel_inflight(execution_id)

    async def _reap_hung_tasks(self) -> None:
        cutoff = utc_now() - timedelta(
            seconds=settings.max_task_timeout_seconds + settings.worker_heartbeat_interval_seconds * 2
        )
        async with self._session_factory() as session:
            result = await session.execute(
                select(ExecutionTask).where(
                    ExecutionTask.status == TaskState.running,
                    (
                        (ExecutionTask.last_heartbeat_at.is_(None) & (ExecutionTask.started_at < cutoff))
                        | (ExecutionTask.last_heartbeat_at < cutoff)
                    ),
                )
            )
            stale = list(result.scalars())
        for item in stale:
            logger.warning("Reaping hung task %s (%s).", item.id, item.task_name)
            async with self._session_factory() as session:
                await self._execution_service.handle_dead_letter(
                    session,
                    DeadLetteredJob(
                        id="",
                        execution_task_id=item.id,
                        execution_id=item.execution_id,
                        task_id=item.task_id or "",
                        tenant_id="",
                        attempts=0,
                        error="Task heartbeat was lost; the worker likely crashed or hung.",
                    ),
                )

    async def _finalize_orphaned_executions(self) -> None:
        async with self._session_factory() as session:
            result = await session.execute(
                select(Execution)
                .where(Execution.status.in_([ExecutionStatus.running, ExecutionStatus.pending]))
                .order_by(Execution.updated_at.asc())
                .limit(200)
            )
            executions = list(result.scalars())

        for execution in executions:
            async with self._session_factory() as session:
                tasks = list(
                    (
                        await session.execute(select(ExecutionTask).where(ExecutionTask.execution_id == execution.id))
                    ).scalars()
                )
                if not tasks or any(item.status in ACTIVE_STATES for item in tasks):
                    continue
                await self._execution_service.finalize_execution(session, execution.id)
