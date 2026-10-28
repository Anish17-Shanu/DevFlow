from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
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
    cancelled = "cancelled"


class TaskState(str, enum.Enum):
    pending = "pending"
    queued = "queued"
    running = "running"
    success = "success"
    failed = "failed"
    retrying = "retrying"
    cancelled = "cancelled"
    skipped = "skipped"


class QueueJobState(str, enum.Enum):
    queued = "queued"
    leased = "leased"
    completed = "completed"
    cancelled = "cancelled"
    failed = "failed"


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)


class ApiKey(Base):
    __tablename__ = "api_keys"
    __table_args__ = (
        UniqueConstraint("key_hash", name="uq_api_keys_hash"),
        Index("ix_api_keys_tenant_id", "tenant_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    role: Mapped[str] = mapped_column(String(16), default="viewer", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    tenant: Mapped[Tenant] = relationship("Tenant")


class Workflow(Base):
    __tablename__ = "workflows"
    __table_args__ = (
        Index("ix_workflows_tenant_created", "tenant_id", "created_at"),
        UniqueConstraint("tenant_id", "name", name="uq_workflows_tenant_name"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    current_revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)

    tasks: Mapped[list[TaskDefinition]] = relationship(
        "TaskDefinition",
        back_populates="workflow",
        cascade="all, delete-orphan",
        order_by="TaskDefinition.created_at",
    )
    revisions: Mapped[list[WorkflowRevision]] = relationship(
        "WorkflowRevision",
        back_populates="workflow",
        cascade="all, delete-orphan",
        order_by="WorkflowRevision.revision",
    )
    executions: Mapped[list[Execution]] = relationship("Execution", back_populates="workflow")


class WorkflowRevision(Base):
    __tablename__ = "workflow_revisions"
    __table_args__ = (
        UniqueConstraint("workflow_id", "revision", name="uq_workflow_revisions_number"),
        Index("ix_workflow_revisions_tenant_id", "tenant_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    workflow_id: Mapped[str] = mapped_column(ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    document: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_by: Mapped[str] = mapped_column(String(120), default="system", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)

    workflow: Mapped[Workflow] = relationship("Workflow", back_populates="revisions")


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
    execution_tasks: Mapped[list[ExecutionTask]] = relationship("ExecutionTask", back_populates="task")


class Execution(Base):
    __tablename__ = "executions"
    __table_args__ = (
        Index("ix_executions_tenant_created", "tenant_id", "created_at"),
        Index("ix_executions_tenant_status", "tenant_id", "status"),
        Index("ix_executions_workflow_id", "workflow_id"),
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_executions_tenant_idempotency"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    workflow_id: Mapped[str] = mapped_column(ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False)
    workflow_revision_id: Mapped[str | None] = mapped_column(
        ForeignKey("workflow_revisions.id", ondelete="SET NULL"), nullable=True
    )
    workflow_name: Mapped[str] = mapped_column(String(255), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[ExecutionStatus] = mapped_column(
        Enum(ExecutionStatus), default=ExecutionStatus.pending, nullable=False
    )
    cancellation_requested: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    triggered_by: Mapped[str] = mapped_column(String(120), default="system", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    workflow: Mapped[Workflow] = relationship("Workflow", back_populates="executions")
    execution_tasks: Mapped[list[ExecutionTask]] = relationship(
        "ExecutionTask",
        back_populates="execution",
        cascade="all, delete-orphan",
    )
    logs: Mapped[list[ExecutionLog]] = relationship(
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
    task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True)
    task_name: Mapped[str] = mapped_column(String(255), nullable=False)
    dependencies: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    config: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[TaskState] = mapped_column(Enum(TaskState), default=TaskState.pending, nullable=False)
    retries: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    worker_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    execution: Mapped[Execution] = relationship("Execution", back_populates="execution_tasks")
    task: Mapped[TaskDefinition | None] = relationship("TaskDefinition", back_populates="execution_tasks")


class ExecutionLog(Base):
    __tablename__ = "execution_logs"
    __table_args__ = (
        Index("ix_execution_logs_execution_id", "execution_id"),
        Index("ix_execution_logs_created_at", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    execution_id: Mapped[str] = mapped_column(ForeignKey("executions.id", ondelete="CASCADE"), nullable=False)
    task_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
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
        Index("ix_queue_jobs_tenant_state", "tenant_id", "state"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    workflow_id: Mapped[str] = mapped_column(String(36), nullable=False)
    execution_task_id: Mapped[str] = mapped_column(String(36), nullable=False)
    execution_id: Mapped[str] = mapped_column(String(36), nullable=False)
    task_id: Mapped[str] = mapped_column(String(36), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    available_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    dead_lettered: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
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


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_tenant_created", "tenant_id", "created_at"),
        Index("ix_audit_logs_resource", "resource_type", "resource_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    actor_key_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    actor_label: Mapped[str] = mapped_column(String(120), default="system", nullable=False)
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(80), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(80), nullable=False)
    details: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)


class SecretRecord(Base):
    __tablename__ = "secrets"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_secrets_tenant_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)


class WebhookEndpoint(Base):
    __tablename__ = "webhook_endpoints"
    __table_args__ = (Index("ix_webhook_endpoints_tenant_id", "tenant_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    secret: Mapped[str] = mapped_column(String(255), nullable=False)
    events: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)


class WebhookDelivery(Base):
    __tablename__ = "webhook_deliveries"
    __table_args__ = (
        Index("ix_webhook_deliveries_status_next", "status", "next_attempt_at"),
        Index("ix_webhook_deliveries_tenant_id", "tenant_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    endpoint_id: Mapped[str] = mapped_column(ForeignKey("webhook_endpoints.id", ondelete="CASCADE"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="pending", nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class WorkflowSchedule(Base):
    __tablename__ = "workflow_schedules"
    __table_args__ = (Index("ix_workflow_schedules_next_run", "is_enabled", "next_run_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    workflow_id: Mapped[str] = mapped_column(ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False)
    cron: Mapped[str | None] = mapped_column(String(120), nullable=True)
    interval_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    next_run_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class OutboxEvent(Base):
    __tablename__ = "outbox_events"
    __table_args__ = (Index("ix_outbox_events_processed_created", "processed_at", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    execution_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
