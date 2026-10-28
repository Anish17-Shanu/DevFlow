from __future__ import annotations

import asyncio
import logging
import os
import socket
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.core.config import settings
from backend.core.context import binding
from backend.core.database import SessionLocal
from backend.core.metrics import WORKERS_ONLINE
from backend.core.time import utc_now
from backend.models.entities import WorkerRecord
from backend.queue.job_queue import DatabaseJobQueue
from backend.services.execution_service import ExecutionService

logger = logging.getLogger(__name__)


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
        self._draining = False

    def _instance_prefix(self) -> str:
        if settings.worker_instance_id:
            return settings.worker_instance_id[:80]
        host = socket.gethostname().split(".")[0][:24]
        return f"{host}-{os.getpid()}-{uuid.uuid4().hex[:6]}"

    async def start(self, worker_count: int | None = None) -> None:
        if self._running:
            return
        self._running = True
        self._draining = False
        count = worker_count or settings.worker_count
        prefix = self._instance_prefix()
        for index in range(count):
            worker_id = f"{prefix}-worker-{index + 1}"[:120]
            snapshot = WorkerSnapshot(worker_id=worker_id, last_seen_at=utc_now())
            self._snapshots[worker_id] = snapshot
            await self._persist_snapshot(snapshot, is_active=True, force=True)
            self._tasks.append(asyncio.create_task(self._run_worker(worker_id)))
        WORKERS_ONLINE.set(count)

    async def stop(self) -> None:
        self._draining = True
        grace = settings.worker_shutdown_grace_seconds
        if self._tasks:
            _, pending = await asyncio.wait(self._tasks, timeout=grace)
            for task in pending:
                logger.warning("Worker did not drain within %ss; cancelling.", grace)
                task.cancel()
            for task in self._tasks:
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._running = False
        for snapshot in self._snapshots.values():
            snapshot.state = "stopped"
            snapshot.current_execution_id = None
            snapshot.current_task_id = None
            snapshot.last_seen_at = utc_now()
            await self._persist_snapshot(snapshot, is_active=False, force=True)
        self._tasks.clear()
        WORKERS_ONLINE.set(0)

    async def _run_worker(self, worker_id: str) -> None:
        snapshot = self._snapshots[worker_id]
        timeout = max(settings.worker_poll_interval_ms / 1000, 0.25)
        with binding(worker_id=worker_id):
            while self._running and not self._draining:
                snapshot.last_seen_at = utc_now()
                await self._persist_snapshot(snapshot, is_active=True)
                await self._process_dead_letters()
                try:
                    job = await self.queue.dequeue(worker_id=worker_id, timeout=timeout)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.exception("Worker %s failed to poll the queue.", worker_id)
                    snapshot.failed_jobs += 1
                    snapshot.last_error = str(exc)
                    snapshot.state = "error"
                    snapshot.last_seen_at = utc_now()
                    await self._persist_snapshot(snapshot, is_active=True, force=True)
                    await asyncio.sleep(timeout)
                    continue
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
                            job=job,
                        )
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.exception("Worker %s failed to execute job %s.", worker_id, job.id)
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

    async def _process_dead_letters(self) -> None:
        for dead_letter in self.queue.drain_dead_letters():
            try:
                async with self._session_factory() as session:
                    await self.execution_service.handle_dead_letter(session, dead_letter)
            except Exception:
                logger.exception("Failed to finalize dead-lettered job %s.", dead_letter.id)

    async def _renew_lease_loop(self, job_id: str, worker_id: str, snapshot: WorkerSnapshot) -> None:
        interval = max(min(self.queue.lease_seconds / 2, settings.worker_heartbeat_interval_seconds), 1)
        while self._running:
            await asyncio.sleep(interval)
            try:
                renewed = await self.queue.renew_lease(job_id, worker_id)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Worker %s failed to renew lease for job %s.", worker_id, job_id)
                return
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

        try:
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
        except SQLAlchemyError:
            logger.exception("Failed to persist heartbeat for worker %s.", snapshot.worker_id)
            return
        self._last_persisted_at[snapshot.worker_id] = now

    async def snapshots(self) -> list[WorkerSnapshot]:
        try:
            async with self._session_factory() as session:
                result = await session.execute(
                    select(WorkerRecord).where(WorkerRecord.is_active.is_(True)).order_by(WorkerRecord.worker_id.asc())
                )
                records = result.scalars().all()
        except SQLAlchemyError:
            logger.exception("Failed to load worker snapshots.")
            return []

        stale_after = settings.worker_heartbeat_interval_seconds * 3
        return [
            WorkerSnapshot(
                worker_id=record.worker_id,
                state=(
                    "offline"
                    if record.last_seen_at is not None
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
        ]
