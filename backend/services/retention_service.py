from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.core.config import settings
from backend.core.time import utc_now
from backend.models.entities import (
    Execution,
    ExecutionLog,
    ExecutionTask,
    OutboxEvent,
    QueueJobRecord,
    QueueJobState,
    WorkerRecord,
)

logger = logging.getLogger(__name__)


class RetentionService:
    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._session_factory = session_factory
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
                logger.exception("Retention pass failed; retrying.")
            await asyncio.sleep(settings.retention_interval_seconds)

    async def run_once(self) -> dict[str, int]:
        now = utc_now()
        log_cutoff = now - timedelta(days=settings.log_retention_days)
        execution_cutoff = now - timedelta(days=settings.execution_retention_days)
        queue_cutoff = now - timedelta(days=settings.queue_retention_days)
        worker_cutoff = now - timedelta(days=settings.worker_retention_days)
        deleted: dict[str, int] = {}

        async with self._session_factory() as session:
            old_executions = select(Execution.id).where(
                Execution.status.in_(["success", "failed", "cancelled"]),
                Execution.finished_at.is_not(None),
                Execution.finished_at < execution_cutoff,
            )
            result = await session.execute(delete(ExecutionLog).where(ExecutionLog.execution_id.in_(old_executions)))
            deleted["logs"] = int(result.rowcount or 0)
            deleted["logs"] += int(
                (await session.execute(delete(ExecutionLog).where(ExecutionLog.created_at < log_cutoff))).rowcount or 0
            )
            await session.execute(delete(ExecutionTask).where(ExecutionTask.execution_id.in_(old_executions)))
            result = await session.execute(delete(Execution).where(Execution.id.in_(old_executions)))
            deleted["executions"] = int(result.rowcount or 0)

            result = await session.execute(
                delete(QueueJobRecord).where(
                    QueueJobRecord.state.in_([QueueJobState.completed, QueueJobState.cancelled, QueueJobState.failed]),
                    QueueJobRecord.completed_at.is_not(None),
                    QueueJobRecord.completed_at < queue_cutoff,
                )
            )
            deleted["queue_jobs"] = int(result.rowcount or 0)

            result = await session.execute(
                delete(OutboxEvent).where(
                    OutboxEvent.processed_at.is_not(None),
                    OutboxEvent.processed_at < log_cutoff,
                )
            )
            deleted["outbox_events"] = int(result.rowcount or 0)

            result = await session.execute(
                delete(WorkerRecord).where(
                    WorkerRecord.is_active.is_(False),
                    WorkerRecord.last_seen_at.is_not(None),
                    WorkerRecord.last_seen_at < worker_cutoff,
                )
            )
            deleted["workers"] = int(result.rowcount or 0)
            await session.commit()

        if any(deleted.values()):
            logger.info("Retention pass removed records: %s", deleted)
        return deleted
