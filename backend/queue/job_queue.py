from __future__ import annotations

import asyncio
import heapq
import itertools
from dataclasses import dataclass, field
from datetime import datetime, timedelta


@dataclass(order=True)
class QueueJob:
    sort_key: tuple = field(init=False, repr=False)
    execution_task_id: str = field(compare=False)
    execution_id: str = field(compare=False)
    task_id: str = field(compare=False)
    priority: int = field(default=0, compare=False)
    available_at: datetime = field(default_factory=datetime.utcnow, compare=False)
    retry_count: int = field(default=0, compare=False)

    def bind_order(self, sequence: int) -> None:
        self.sort_key = (self.available_at.timestamp(), -self.priority, sequence)


class InMemoryJobQueue:
    def __init__(self) -> None:
        self._heap: list[QueueJob] = []
        self._in_flight: dict[str, QueueJob] = {}
        self._sequence = itertools.count()
        self._condition = asyncio.Condition()
        self._total_enqueued = 0
        self._total_processed = 0

    async def enqueue(self, job: QueueJob) -> None:
        async with self._condition:
            job.bind_order(next(self._sequence))
            heapq.heappush(self._heap, job)
            self._total_enqueued += 1
            self._condition.notify_all()

    async def dequeue(self, timeout: float = 1.0) -> QueueJob | None:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        async with self._condition:
            while True:
                if self._heap:
                    job = self._heap[0]
                    now = datetime.utcnow()
                    if job.available_at <= now:
                        ready = heapq.heappop(self._heap)
                        self._in_flight[ready.execution_task_id] = ready
                        return ready

                    wait_for = min((job.available_at - now).total_seconds(), max(deadline - loop.time(), 0.0))
                    if wait_for <= 0:
                        return None
                    await asyncio.wait_for(self._condition.wait(), timeout=wait_for)
                    continue

                remaining = deadline - loop.time()
                if remaining <= 0:
                    return None
                await asyncio.wait_for(self._condition.wait(), timeout=remaining)

    async def acknowledge(self, execution_task_id: str) -> None:
        async with self._condition:
            if execution_task_id in self._in_flight:
                self._in_flight.pop(execution_task_id, None)
                self._total_processed += 1

    def stats(self) -> dict[str, int]:
        now = datetime.utcnow()
        delayed = sum(1 for job in self._heap if job.available_at > now)
        ready = len(self._heap) - delayed
        return {
            "queued_jobs": ready,
            "delayed_jobs": delayed,
            "in_flight_jobs": len(self._in_flight),
            "total_enqueued": self._total_enqueued,
            "total_processed": self._total_processed,
        }
