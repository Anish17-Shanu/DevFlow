from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Enum, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.database import Base
from backend.core.time import utc_now


def generate_uuid() -> str:
    return str(uuid.uuid4())


class ExecutionStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    success = "success"
    failed = "failed"


class TaskState(str, enum.Enum):
    pending = "pending"
    queued = "queued"
    running = "running"
    success = "success"
    failed = "failed"
    retrying = "retrying"


class QueueJobState(str, enum.Enum):
    queued = "queued"
    leased = "leased"
    completed = "completed"


class Workflow(Base):
    __tablename__ = "workflows"
    __table_args__ = (Index("ix_workflows_created_at", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)

    tasks: Mapped[list["TaskDefinition"]] = relationship(
        "TaskDefinition",
        back_populates="workflow",
        cascade="all, delete-orphan",
        order_by="TaskDefinition.created_at",
    )
    executions: Mapped[list["Execution"]] = relationship("Execution", back_populates="workflow")


class TaskDefinition(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        UniqueConstraint("workflow_id", "name", name="uq_task_workflow_name"),
        Index("ix_tasks_workflow_id", "workflow_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    workflow_id: Mapped[str] = mapped_column(ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    dependencies: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    config: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)

    workflow: Mapped[Workflow] = relationship("Workflow", back_populates="tasks")
    execution_tasks: Mapped[list["ExecutionTask"]] = relationship("ExecutionTask", back_populates="task")


class Execution(Base):
    __tablename__ = "executions"
    __table_args__ = (
        Index("ix_executions_workflow_id", "workflow_id"),
        Index("ix_executions_status", "status"),
        Index("ix_executions_created_at", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    workflow_id: Mapped[str] = mapped_column(ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[ExecutionStatus] = mapped_column(Enum(ExecutionStatus), default=ExecutionStatus.pending, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    workflow: Mapped[Workflow] = relationship("Workflow", back_populates="executions")
    execution_tasks: Mapped[list["ExecutionTask"]] = relationship(
        "ExecutionTask",
        back_populates="execution",
        cascade="all, delete-orphan",
    )
    logs: Mapped[list["ExecutionLog"]] = relationship(
        "ExecutionLog",
        back_populates="execution",
        cascade="all, delete-orphan",
        order_by="ExecutionLog.created_at",
    )


class ExecutionTask(Base):
    __tablename__ = "execution_tasks"
    __table_args__ = (
        UniqueConstraint("execution_id", "task_id", name="uq_execution_task_pair"),
        Index("ix_execution_tasks_execution_id", "execution_id"),
        Index("ix_execution_tasks_status", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    execution_id: Mapped[str] = mapped_column(ForeignKey("executions.id", ondelete="CASCADE"), nullable=False)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[TaskState] = mapped_column(Enum(TaskState), default=TaskState.pending, nullable=False)
    retries: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    worker_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    execution: Mapped[Execution] = relationship("Execution", back_populates="execution_tasks")
    task: Mapped[TaskDefinition] = relationship("TaskDefinition", back_populates="execution_tasks")


class ExecutionLog(Base):
    __tablename__ = "execution_logs"
    __table_args__ = (
        Index("ix_execution_logs_execution_id", "execution_id"),
        Index("ix_execution_logs_created_at", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    execution_id: Mapped[str] = mapped_column(ForeignKey("executions.id", ondelete="CASCADE"), nullable=False)
    task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True)
    level: Mapped[str] = mapped_column(String(24), default="INFO", nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)

    execution: Mapped[Execution] = relationship("Execution", back_populates="logs")


class QueueJobRecord(Base):
    __tablename__ = "queue_jobs"
    __table_args__ = (
        Index("ix_queue_jobs_state_available_at", "state", "available_at"),
        Index("ix_queue_jobs_execution_task_id", "execution_task_id"),
        Index("ix_queue_jobs_lease_expires_at", "lease_expires_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    execution_task_id: Mapped[str] = mapped_column(String(36), nullable=False)
    execution_id: Mapped[str] = mapped_column(String(36), nullable=False)
    task_id: Mapped[str] = mapped_column(String(36), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    available_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    state: Mapped[QueueJobState] = mapped_column(Enum(QueueJobState), default=QueueJobState.queued, nullable=False)
    leased_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    leased_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)


class WorkerRecord(Base):
    __tablename__ = "worker_records"
    __table_args__ = (
        Index("ix_worker_records_last_seen_at", "last_seen_at"),
        Index("ix_worker_records_state", "state"),
    )

    worker_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    state: Mapped[str] = mapped_column(String(32), default="idle", nullable=False)
    current_execution_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    current_task_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    processed_jobs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_jobs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
