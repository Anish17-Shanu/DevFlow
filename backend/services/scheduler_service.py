from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from croniter import croniter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.core.config import settings
from backend.core.security import ApiError
from backend.core.time import utc_now
from backend.models.entities import Workflow, WorkflowSchedule
from backend.services.execution_service import ExecutionService

logger = logging.getLogger(__name__)


def compute_next_run(schedule: WorkflowSchedule, reference=None):
    base = reference or utc_now()
    if schedule.cron:
        next_run = croniter(schedule.cron, base).get_next(datetime)
        if next_run.tzinfo is not None:
            next_run = next_run.astimezone(UTC).replace(tzinfo=None)
        return next_run
    return base + timedelta(seconds=schedule.interval_seconds or 60)


class SchedulerService:
    def __init__(self, session_factory: async_sessionmaker, execution_service: ExecutionService) -> None:
        self._session_factory = session_factory
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
                logger.exception("Scheduler iteration failed; retrying.")
            await asyncio.sleep(settings.scheduler_interval_seconds)

    async def run_once(self) -> int:
        now = utc_now()
        triggered = 0
        async with self._session_factory() as session:
            result = await session.execute(
                select(WorkflowSchedule)
                .where(WorkflowSchedule.is_enabled.is_(True), WorkflowSchedule.next_run_at <= now)
                .order_by(WorkflowSchedule.next_run_at.asc())
                .limit(50)
            )
            schedules = list(result.scalars())
            for schedule in schedules:
                workflow = await session.get(Workflow, schedule.workflow_id)
                if workflow is None or workflow.is_archived:
                    schedule.is_enabled = False
                    continue
                idempotency_key = f"schedule:{schedule.id}:{schedule.next_run_at.isoformat()}"
                try:
                    await self._execution_service.trigger_workflow(
                        session,
                        schedule.tenant_id,
                        schedule.workflow_id,
                        actor="scheduler",
                        idempotency_key=idempotency_key,
                    )
                    triggered += 1
                except ApiError as exc:
                    logger.warning("Scheduled run for workflow %s skipped: %s", schedule.workflow_id, exc.message)
                schedule.last_run_at = now
                schedule.next_run_at = compute_next_run(schedule, now)
            await session.commit()
        return triggered
