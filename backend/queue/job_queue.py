from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.core.config import settings
from backend.core.time import utc_now
from backend.models.entities import QueueJobRecord, QueueJobState


@dataclass(order=True)
class QueueJob:
    sort_key: tuple = field(init=False, repr=False, compare=True)
    id: str = field(default_factory=lambda: str(uuid.uuid4()), compare=False)
    execution_task_id: str = field(compare=False, default="")
    execution_id: str = field(compare=False, default="")
    task_id: str = field(compare=False, default="")
    priority: int = field(default=0, compare=False)
    available_at: datetime = field(default_factory=utc_now, compare=False)
    retry_count: int = field(default=0, compare=False)

    def __post_init__(self) -> None:
        self.sort_key = (self.available_at.timestamp(), -self.priority, self.id)


class DatabaseJobQueue:
    def __init__(self, session_factory: async_sessionmaker):
        self._session_factory = session_factory

    @property
    def lease_seconds(self) -> int:
        return settings.queue_lease_seconds

    async def enqueue(self, job: QueueJob, session=None) -> None:
        record = QueueJobRecord(
            id=job.id,
            execution_task_id=job.execution_task_id,
            execution_id=job.execution_id,
            task_id=job.task_id,
            priority=job.priority,
            available_at=job.available_at,
            retry_count=job.retry_count,
            state=QueueJobState.queued,
        )

        if session is not None:
            session.add(record)
            return

        async with self._session_factory() as owned_session:
            owned_session.add(record)
            await owned_session.commit()

    async def dequeue(self, worker_id: str, timeout: float = 1.0) -> QueueJob | None:
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            await self.requeue_stale_jobs()
            job = await self._claim_next_available(worker_id)
            if job:
                return job

            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                return None
            await asyncio.sleep(min(0.25, remaining))

    async def _claim_next_available(self, worker_id: str) -> QueueJob | None:
        now = utc_now()
        lease_expires_at = now + timedelta(seconds=self.lease_seconds)

        async with self._session_factory() as session:
            result = await session.execute(
                select(QueueJobRecord)
                .where(
                    QueueJobRecord.state == QueueJobState.queued,
                    QueueJobRecord.available_at <= now,
                )
                .order_by(
                    QueueJobRecord.priority.desc(),
                    QueueJobRecord.available_at.asc(),
                    QueueJobRecord.created_at.asc(),
                )
                .limit(1)
            )
            candidate = result.scalars().first()
            if not candidate:
                return None

            claim = await session.execute(
                update(QueueJobRecord)
                .where(
                    QueueJobRecord.id == candidate.id,
                    QueueJobRecord.state == QueueJobState.queued,
                )
                .values(
                    state=QueueJobState.leased,
                    leased_by=worker_id,
                    leased_at=now,
                    lease_expires_at=lease_expires_at,
                )
                .returning(
                    QueueJobRecord.id,
                    QueueJobRecord.execution_task_id,
                    QueueJobRecord.execution_id,
                    QueueJobRecord.task_id,
                    QueueJobRecord.priority,
                    QueueJobRecord.available_at,
                    QueueJobRecord.retry_count,
                )
            )
            row = claim.first()
            if not row:
                await session.rollback()
                return None

            await session.commit()
            return QueueJob(
                id=row.id,
                execution_task_id=row.execution_task_id,
                execution_id=row.execution_id,
                task_id=row.task_id,
                priority=row.priority,
                available_at=row.available_at,
                retry_count=row.retry_count,
            )

    async def renew_lease(self, job_id: str, worker_id: str) -> bool:
        now = utc_now()
        lease_expires_at = now + timedelta(seconds=self.lease_seconds)
        async with self._session_factory() as session:
            result = await session.execute(
                update(QueueJobRecord)
                .where(
                    QueueJobRecord.id == job_id,
                    QueueJobRecord.state == QueueJobState.leased,
                    QueueJobRecord.leased_by == worker_id,
                )
                .values(lease_expires_at=lease_expires_at)
            )
            await session.commit()
            return bool(result.rowcount)

    async def acknowledge(self, job_id: str, session=None) -> None:
        values = {
            "state": QueueJobState.completed,
            "completed_at": utc_now(),
            "leased_by": None,
            "leased_at": None,
            "lease_expires_at": None,
        }
        if session is not None:
            await session.execute(update(QueueJobRecord).where(QueueJobRecord.id == job_id).values(**values))
            return

        async with self._session_factory() as owned_session:
            await owned_session.execute(update(QueueJobRecord).where(QueueJobRecord.id == job_id).values(**values))
            await owned_session.commit()

    async def requeue_stale_jobs(self) -> int:
        async with self._session_factory() as session:
            result = await session.execute(
                update(QueueJobRecord)
                .where(
                    QueueJobRecord.state == QueueJobState.leased,
                    QueueJobRecord.lease_expires_at.is_not(None),
                    QueueJobRecord.lease_expires_at < utc_now(),
                )
                .values(
                    state=QueueJobState.queued,
                    leased_by=None,
                    leased_at=None,
                    lease_expires_at=None,
                )
            )
            await session.commit()
            return int(result.rowcount or 0)

    async def stats(self) -> dict[str, int | bool | str]:
        now = utc_now()
        try:
            async with self._session_factory() as session:
                queued_jobs = await session.scalar(
                    select(func.count()).select_from(QueueJobRecord).where(
                        QueueJobRecord.state == QueueJobState.queued,
                        QueueJobRecord.available_at <= now,
                    )
                )
                delayed_jobs = await session.scalar(
                    select(func.count()).select_from(QueueJobRecord).where(
                        QueueJobRecord.state == QueueJobState.queued,
                        QueueJobRecord.available_at > now,
                    )
                )
                in_flight_jobs = await session.scalar(
                    select(func.count()).select_from(QueueJobRecord).where(QueueJobRecord.state == QueueJobState.leased)
                )
                total_enqueued = await session.scalar(select(func.count()).select_from(QueueJobRecord))
                total_processed = await session.scalar(
                    select(func.count()).select_from(QueueJobRecord).where(QueueJobRecord.state == QueueJobState.completed)
                )
        except SQLAlchemyError:
            queued_jobs = delayed_jobs = in_flight_jobs = total_enqueued = total_processed = 0

        return {
            "queued_jobs": int(queued_jobs or 0),
            "delayed_jobs": int(delayed_jobs or 0),
            "in_flight_jobs": int(in_flight_jobs or 0),
            "total_enqueued": int(total_enqueued or 0),
            "total_processed": int(total_processed or 0),
            "queue_backend": "database",
            "is_durable": True,
        }
