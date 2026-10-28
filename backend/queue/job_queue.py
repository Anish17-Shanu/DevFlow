from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import case, func, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import aliased

from backend.core.config import settings
from backend.core.time import utc_now
from backend.models.entities import QueueJobRecord, QueueJobState

logger = logging.getLogger(__name__)


@dataclass(order=True)
class QueueJob:
    sort_key: tuple = field(init=False, repr=False, compare=True)
    id: str = field(default_factory=lambda: str(uuid.uuid4()), compare=False)
    execution_task_id: str = field(compare=False, default="")
    execution_id: str = field(compare=False, default="")
    task_id: str = field(compare=False, default="")
    tenant_id: str = field(compare=False, default="")
    workflow_id: str = field(compare=False, default="")
    priority: int = field(default=0, compare=False)
    available_at: datetime = field(default_factory=utc_now, compare=False)
    retry_count: int = field(default=0, compare=False)
    attempts: int = field(default=0, compare=False)
    max_attempts: int = field(default=settings.queue_poison_max_attempts, compare=False)
    enqueued_at: datetime = field(default_factory=utc_now, compare=False)

    def __post_init__(self) -> None:
        self.sort_key = (self.available_at.timestamp(), -self.priority, self.id)


@dataclass
class DeadLetteredJob:
    id: str
    execution_task_id: str
    execution_id: str
    task_id: str
    tenant_id: str
    attempts: int
    error: str


class DatabaseJobQueue:
    def __init__(self, session_factory: async_sessionmaker):
        self._session_factory = session_factory
        self._last_requeue_at = 0.0
        self._dead_letter_buffer: list[DeadLetteredJob] = []
        bind = session_factory.kw.get("bind")
        self._dialect = bind.dialect.name if bind is not None else "sqlite"

    @property
    def lease_seconds(self) -> int:
        return settings.queue_lease_seconds

    @property
    def requeue_interval_seconds(self) -> float:
        return max(1.0, min(self.lease_seconds / 2, 5.0))

    async def enqueue(self, job: QueueJob, session=None) -> None:
        if not job.tenant_id:
            raise ValueError("Queue jobs must carry a tenant_id.")
        record = QueueJobRecord(
            id=job.id,
            tenant_id=job.tenant_id,
            workflow_id=job.workflow_id,
            execution_task_id=job.execution_task_id,
            execution_id=job.execution_id,
            task_id=job.task_id,
            priority=job.priority,
            available_at=job.available_at,
            retry_count=job.retry_count,
            attempts=job.attempts,
            max_attempts=job.max_attempts,
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
            await self._requeue_stale_jobs_if_due()
            job = await self._claim_next_available(worker_id)
            if job:
                return job

            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                return None
            await asyncio.sleep(min(0.25, remaining))

    async def _requeue_stale_jobs_if_due(self) -> None:
        now = asyncio.get_running_loop().time()
        if now - self._last_requeue_at < self.requeue_interval_seconds:
            return
        self._last_requeue_at = now
        try:
            await self.requeue_stale_jobs()
        except SQLAlchemyError:
            logger.exception("Stale lease reaper failed.")

    def _claim_query(self, candidate_alias):
        leased_count = (
            select(func.count())
            .select_from(QueueJobRecord)
            .where(
                QueueJobRecord.state == QueueJobState.leased,
                QueueJobRecord.workflow_id == candidate_alias.workflow_id,
            )
            .scalar_subquery()
        )
        return leased_count < settings.max_concurrent_tasks_per_workflow

    async def _claim_next_available(self, worker_id: str) -> QueueJob | None:
        now = utc_now()
        lease_expires_at = now + timedelta(seconds=self.lease_seconds)
        aged_cutoff = now - timedelta(seconds=settings.queue_aging_seconds)
        candidate = aliased(QueueJobRecord)

        statement = (
            select(candidate)
            .where(
                candidate.state == QueueJobState.queued,
                candidate.available_at <= now,
                self._claim_query(candidate),
            )
            .order_by(
                case((candidate.available_at <= aged_cutoff, 0), else_=1).asc(),
                candidate.priority.desc(),
                candidate.available_at.asc(),
                candidate.created_at.asc(),
            )
            .limit(1)
        )
        if self._dialect == "postgresql":
            statement = statement.with_for_update(skip_locked=True)

        try:
            async with self._session_factory() as session:
                result = await session.execute(statement)
                job = result.scalars().first()
                if not job:
                    return None

                claim = await session.execute(
                    update(QueueJobRecord)
                    .where(
                        QueueJobRecord.id == job.id,
                        QueueJobRecord.state == QueueJobState.queued,
                    )
                    .values(
                        state=QueueJobState.leased,
                        leased_by=worker_id,
                        leased_at=now,
                        lease_expires_at=lease_expires_at,
                        attempts=QueueJobRecord.attempts + 1,
                    )
                    .returning(
                        QueueJobRecord.id,
                        QueueJobRecord.tenant_id,
                        QueueJobRecord.workflow_id,
                        QueueJobRecord.execution_task_id,
                        QueueJobRecord.execution_id,
                        QueueJobRecord.task_id,
                        QueueJobRecord.priority,
                        QueueJobRecord.available_at,
                        QueueJobRecord.retry_count,
                        QueueJobRecord.attempts,
                        QueueJobRecord.max_attempts,
                        QueueJobRecord.created_at,
                    )
                )
                row = claim.first()
                if not row:
                    await session.rollback()
                    return None
                await session.commit()
        except SQLAlchemyError:
            logger.exception("Failed to claim a queue job.")
            return None

        return QueueJob(
            id=row.id,
            tenant_id=row.tenant_id,
            workflow_id=row.workflow_id,
            execution_task_id=row.execution_task_id,
            execution_id=row.execution_id,
            task_id=row.task_id,
            priority=row.priority,
            available_at=row.available_at,
            retry_count=row.retry_count,
            attempts=row.attempts,
            max_attempts=row.max_attempts,
            enqueued_at=row.created_at,
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
            await session.execute(
                update(QueueJobRecord)
                .where(QueueJobRecord.id == job_id, QueueJobRecord.state != QueueJobState.cancelled)
                .values(**values)
            )
            return

        async with self._session_factory() as owned_session:
            await owned_session.execute(
                update(QueueJobRecord)
                .where(QueueJobRecord.id == job_id, QueueJobRecord.state != QueueJobState.cancelled)
                .values(**values)
            )
            await owned_session.commit()

    async def cancel_execution_jobs(self, execution_id: str, session) -> None:
        await session.execute(
            update(QueueJobRecord)
            .where(
                QueueJobRecord.execution_id == execution_id,
                QueueJobRecord.state.in_([QueueJobState.queued, QueueJobState.leased]),
            )
            .values(state=QueueJobState.cancelled, completed_at=utc_now(), lease_expires_at=None)
        )

    async def cancel_task_jobs(self, execution_task_id: str, session) -> None:
        await session.execute(
            update(QueueJobRecord)
            .where(
                QueueJobRecord.execution_task_id == execution_task_id,
                QueueJobRecord.state == QueueJobState.queued,
            )
            .values(state=QueueJobState.cancelled, completed_at=utc_now())
        )

    async def requeue_stale_jobs(self) -> list[DeadLetteredJob]:
        now = utc_now()
        dead_letters: list[DeadLetteredJob] = []
        async with self._session_factory() as session:
            statement = select(QueueJobRecord).where(
                QueueJobRecord.state == QueueJobState.leased,
                QueueJobRecord.lease_expires_at.is_not(None),
                QueueJobRecord.lease_expires_at < now,
            )
            if self._dialect == "postgresql":
                statement = statement.with_for_update(skip_locked=True)
            result = await session.execute(statement)
            expired = list(result.scalars())

            for job in expired:
                if job.attempts >= job.max_attempts:
                    job.state = QueueJobState.failed
                    job.dead_lettered = True
                    job.completed_at = now
                    job.lease_expires_at = None
                    job.last_error = f"Job exceeded {job.max_attempts} attempts after repeated worker loss."
                    dead_letters.append(
                        DeadLetteredJob(
                            id=job.id,
                            execution_task_id=job.execution_task_id,
                            execution_id=job.execution_id,
                            task_id=job.task_id,
                            tenant_id=job.tenant_id,
                            attempts=job.attempts,
                            error=job.last_error,
                        )
                    )
                else:
                    job.state = QueueJobState.queued
                    job.leased_by = None
                    job.leased_at = None
                    job.lease_expires_at = None
                    job.last_error = f"Lease expired after attempt {job.attempts}."
            await session.commit()
        self._dead_letter_buffer.extend(dead_letters)
        return dead_letters

    def drain_dead_letters(self) -> list[DeadLetteredJob]:
        items = list(self._dead_letter_buffer)
        self._dead_letter_buffer.clear()
        return items

    async def dead_letter_count(self) -> int:
        async with self._session_factory() as session:
            return int(
                await session.scalar(
                    select(func.count()).select_from(QueueJobRecord).where(QueueJobRecord.dead_lettered.is_(True))
                )
                or 0
            )

    async def count_dead_letters(self, tenant_id: str) -> int:
        async with self._session_factory() as session:
            return int(
                await session.scalar(
                    select(func.count())
                    .select_from(QueueJobRecord)
                    .where(
                        QueueJobRecord.tenant_id == tenant_id,
                        QueueJobRecord.dead_lettered.is_(True),
                    )
                )
                or 0
            )

    async def get_dead_letter(self, tenant_id: str, job_id: str) -> QueueJobRecord | None:
        async with self._session_factory() as session:
            return await session.scalar(
                select(QueueJobRecord).where(
                    QueueJobRecord.id == job_id,
                    QueueJobRecord.tenant_id == tenant_id,
                    QueueJobRecord.dead_lettered.is_(True),
                )
            )

    async def list_dead_letters(self, tenant_id: str, limit: int = 50, offset: int = 0) -> list[QueueJobRecord]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(QueueJobRecord)
                .where(
                    QueueJobRecord.tenant_id == tenant_id,
                    QueueJobRecord.dead_lettered.is_(True),
                )
                .order_by(QueueJobRecord.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
            return list(result.scalars())

    async def replay_dead_letter(self, tenant_id: str, job_id: str) -> QueueJobRecord | None:
        async with self._session_factory() as session:
            record = await session.scalar(
                select(QueueJobRecord).where(
                    QueueJobRecord.id == job_id,
                    QueueJobRecord.tenant_id == tenant_id,
                    QueueJobRecord.dead_lettered.is_(True),
                )
            )
            if record is None:
                return None
            record.state = QueueJobState.queued
            record.dead_lettered = False
            record.attempts = 0
            record.available_at = utc_now()
            record.completed_at = None
            record.last_error = None
            await session.commit()
            await session.refresh(record)
            return record

    async def resolve_dead_letter(self, tenant_id: str, job_id: str) -> QueueJobRecord | None:
        async with self._session_factory() as session:
            record = await session.scalar(
                select(QueueJobRecord).where(
                    QueueJobRecord.id == job_id,
                    QueueJobRecord.tenant_id == tenant_id,
                    QueueJobRecord.dead_lettered.is_(True),
                )
            )
            if record is None:
                return None
            record.state = QueueJobState.completed
            record.dead_lettered = False
            record.completed_at = utc_now()
            await session.commit()
            await session.refresh(record)
            return record

    async def stats(self, tenant_id: str | None = None) -> dict[str, int | bool | str | None]:
        now = utc_now()
        healthy = True
        error = None
        conditions = [QueueJobRecord.tenant_id == tenant_id] if tenant_id else []

        try:
            async with self._session_factory() as session:
                queued_jobs = await session.scalar(
                    select(func.count())
                    .select_from(QueueJobRecord)
                    .where(
                        *conditions,
                        QueueJobRecord.state == QueueJobState.queued,
                        QueueJobRecord.available_at <= now,
                    )
                )
                delayed_jobs = await session.scalar(
                    select(func.count())
                    .select_from(QueueJobRecord)
                    .where(*conditions, QueueJobRecord.state == QueueJobState.queued, QueueJobRecord.available_at > now)
                )
                in_flight_jobs = await session.scalar(
                    select(func.count())
                    .select_from(QueueJobRecord)
                    .where(*conditions, QueueJobRecord.state == QueueJobState.leased)
                )
                dead_letter_jobs = await session.scalar(
                    select(func.count())
                    .select_from(QueueJobRecord)
                    .where(*conditions, QueueJobRecord.dead_lettered.is_(True))
                )
                total_enqueued = await session.scalar(
                    select(func.count()).select_from(QueueJobRecord).where(*conditions)
                )
                total_processed = await session.scalar(
                    select(func.count())
                    .select_from(QueueJobRecord)
                    .where(*conditions, QueueJobRecord.state == QueueJobState.completed)
                )
        except SQLAlchemyError:
            logger.exception("Failed to compute queue statistics.")
            healthy = False
            error = "Queue statistics unavailable."
            queued_jobs = delayed_jobs = in_flight_jobs = total_enqueued = total_processed = 0
            dead_letter_jobs = 0
        except Exception:
            logger.exception("Unexpected failure computing queue statistics.")
            healthy = False
            error = "Queue statistics unavailable."
            queued_jobs = delayed_jobs = in_flight_jobs = total_enqueued = total_processed = 0
            dead_letter_jobs = 0

        return {
            "queued_jobs": int(queued_jobs or 0),
            "delayed_jobs": int(delayed_jobs or 0),
            "in_flight_jobs": int(in_flight_jobs or 0),
            "dead_letter_jobs": int(dead_letter_jobs or 0),
            "total_enqueued": int(total_enqueued or 0),
            "total_processed": int(total_processed or 0),
            "queue_backend": "database",
            "is_durable": True,
            "healthy": healthy,
            "error": error,
        }

    async def stale_lease_count(self) -> int:
        async with self._session_factory() as session:
            return int(
                await session.scalar(
                    select(func.count())
                    .select_from(QueueJobRecord)
                    .where(
                        QueueJobRecord.state == QueueJobState.leased,
                        QueueJobRecord.lease_expires_at.is_not(None),
                        QueueJobRecord.lease_expires_at < utc_now(),
                    )
                )
                or 0
            )
