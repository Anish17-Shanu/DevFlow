from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.core.config import settings
from backend.core.database import SessionLocal
from backend.core.time import utc_now
from backend.models.entities import WorkerRecord
from backend.queue.job_queue import DatabaseJobQueue
from backend.services.execution_service import ExecutionService


@dataclass
class WorkerSnapshot:
    worker_id: str
    state: str = "idle"
    current_execution_id: str | None = None
    current_task_id: str | None = None
    processed_jobs: int = 0
    failed_jobs: int = 0
    last_seen_at: datetime | None = None
    last_error: str | None = None


class WorkerManager:
    def __init__(
        self,
        queue: DatabaseJobQueue,
        execution_service: ExecutionService,
        session_factory: async_sessionmaker = SessionLocal,
    ):
        self.queue = queue
        self.execution_service = execution_service
        self._session_factory = session_factory
        self._snapshots: dict[str, WorkerSnapshot] = {}
        self._tasks: list[asyncio.Task] = []
        self._last_persisted_at: dict[str, datetime] = {}
        self._running = False

    async def start(self, worker_count: int | None = None) -> None:
        if self._running:
            return
        self._running = True
        count = worker_count or settings.worker_count
        for index in range(count):
            worker_id = f"worker-{index + 1}"
            snapshot = WorkerSnapshot(worker_id=worker_id, last_seen_at=utc_now())
            self._snapshots[worker_id] = snapshot
            await self._persist_snapshot(snapshot, is_active=True, force=True)
            self._tasks.append(asyncio.create_task(self._run_worker(worker_id)))

    async def stop(self) -> None:
        self._running = False
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
        for snapshot in self._snapshots.values():
            snapshot.state = "stopped"
            snapshot.current_execution_id = None
            snapshot.current_task_id = None
            snapshot.last_seen_at = utc_now()
            await self._persist_snapshot(snapshot, is_active=False, force=True)
        self._tasks.clear()

    async def _run_worker(self, worker_id: str) -> None:
        snapshot = self._snapshots[worker_id]
        timeout = max(settings.worker_poll_interval_ms / 1000, 0.25)

        while self._running:
            snapshot.last_seen_at = utc_now()
            await self._persist_snapshot(snapshot, is_active=True)
            job = await self.queue.dequeue(worker_id=worker_id, timeout=timeout)
            if not job:
                snapshot.state = "idle"
                snapshot.current_execution_id = None
                snapshot.current_task_id = None
                continue

            snapshot.state = "running"
            snapshot.current_execution_id = job.execution_id
            snapshot.current_task_id = job.task_id
            snapshot.last_error = None
            snapshot.last_seen_at = utc_now()
            await self._persist_snapshot(snapshot, is_active=True, force=True)

            renew_task = asyncio.create_task(self._renew_lease_loop(job.id, worker_id, snapshot))
            try:
                async with self._session_factory() as session:
                    await self.execution_service.execute_task(
                        session,
                        job.execution_task_id,
                        worker_id,
                        queue_job_id=job.id,
                    )
            except Exception as exc:
                snapshot.failed_jobs += 1
                snapshot.last_error = str(exc)
                snapshot.state = "error"
                snapshot.last_seen_at = utc_now()
                await self._persist_snapshot(snapshot, is_active=True, force=True)
                await asyncio.sleep(timeout)
            else:
                snapshot.processed_jobs += 1
                snapshot.last_seen_at = utc_now()
                snapshot.state = "idle"
                snapshot.current_execution_id = None
                snapshot.current_task_id = None
                await self._persist_snapshot(snapshot, is_active=True, force=True)
            finally:
                renew_task.cancel()
                try:
                    await renew_task
                except asyncio.CancelledError:
                    pass

    async def _renew_lease_loop(self, job_id: str, worker_id: str, snapshot: WorkerSnapshot) -> None:
        interval = max(min(self.queue.lease_seconds / 2, settings.worker_heartbeat_interval_seconds), 1)
        while self._running:
            await asyncio.sleep(interval)
            renewed = await self.queue.renew_lease(job_id, worker_id)
            if not renewed:
                return
            snapshot.last_seen_at = utc_now()
            await self._persist_snapshot(snapshot, is_active=True)

    async def _persist_snapshot(self, snapshot: WorkerSnapshot, is_active: bool, force: bool = False) -> None:
        last_persisted_at = self._last_persisted_at.get(snapshot.worker_id)
        now = utc_now()
        if not force and last_persisted_at is not None:
            elapsed = (now - last_persisted_at).total_seconds()
            if elapsed < settings.worker_heartbeat_interval_seconds:
                return

        async with self._session_factory() as session:
            record = await session.get(WorkerRecord, snapshot.worker_id)
            if record is None:
                record = WorkerRecord(worker_id=snapshot.worker_id)
                session.add(record)

            record.state = snapshot.state
            record.current_execution_id = snapshot.current_execution_id
            record.current_task_id = snapshot.current_task_id
            record.processed_jobs = snapshot.processed_jobs
            record.failed_jobs = snapshot.failed_jobs
            record.last_seen_at = snapshot.last_seen_at
            record.last_error = snapshot.last_error
            record.is_active = is_active
            record.updated_at = now
            await session.commit()
        self._last_persisted_at[snapshot.worker_id] = now

    async def snapshots(self) -> list[WorkerSnapshot]:
        try:
            async with self._session_factory() as session:
                result = await session.execute(select(WorkerRecord).order_by(WorkerRecord.worker_id.asc()))
                records = result.scalars().all()
        except SQLAlchemyError:
            return []

        stale_after = settings.worker_heartbeat_interval_seconds * 2
        return [
            WorkerSnapshot(
                worker_id=record.worker_id,
                state=(
                    "offline"
                    if record.is_active
                    and record.last_seen_at is not None
                    and (utc_now() - record.last_seen_at).total_seconds() > stale_after
                    else record.state
                ),
                current_execution_id=record.current_execution_id,
                current_task_id=record.current_task_id,
                processed_jobs=record.processed_jobs,
                failed_jobs=record.failed_jobs,
                last_seen_at=record.last_seen_at,
                last_error=record.last_error,
            )
            for record in records
            if record.is_active or record.last_seen_at is not None
        ]
