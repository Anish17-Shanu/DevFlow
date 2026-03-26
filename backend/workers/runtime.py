from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime

from backend.core.config import settings
from backend.core.database import SessionLocal
from backend.queue.job_queue import InMemoryJobQueue
from backend.services.execution_service import ExecutionService


@dataclass
class WorkerSnapshot:
    worker_id: str
    state: str = "idle"
    current_execution_id: str | None = None
    current_task_id: str | None = None
    processed_jobs: int = 0
    last_seen_at: datetime | None = None


class WorkerManager:
    def __init__(self, queue: InMemoryJobQueue, execution_service: ExecutionService):
        self.queue = queue
        self.execution_service = execution_service
        self._snapshots: dict[str, WorkerSnapshot] = {}
        self._tasks: list[asyncio.Task] = []
        self._running = False

    async def start(self, worker_count: int | None = None) -> None:
        if self._running:
            return
        self._running = True
        count = worker_count or settings.worker_count
        for index in range(count):
            worker_id = f"worker-{index + 1}"
            self._snapshots[worker_id] = WorkerSnapshot(worker_id=worker_id, last_seen_at=datetime.utcnow())
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

    async def _run_worker(self, worker_id: str) -> None:
        snapshot = self._snapshots[worker_id]
        timeout = max(settings.worker_poll_interval_ms / 1000, 0.25)

        while self._running:
            snapshot.last_seen_at = datetime.utcnow()
            job = await self.queue.dequeue(timeout=timeout)
            if not job:
                snapshot.state = "idle"
                snapshot.current_execution_id = None
                snapshot.current_task_id = None
                continue

            snapshot.state = "running"
            snapshot.current_execution_id = job.execution_id
            snapshot.current_task_id = job.task_id

            async with SessionLocal() as session:
                await self.execution_service.execute_task(session, job.execution_task_id, worker_id)

            snapshot.processed_jobs += 1
            snapshot.last_seen_at = datetime.utcnow()
            snapshot.state = "idle"
            snapshot.current_execution_id = None
            snapshot.current_task_id = None

    def snapshots(self) -> list[WorkerSnapshot]:
        return list(self._snapshots.values())
