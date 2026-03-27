from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from backend.models.entities import ExecutionStatus, TaskState


class TaskConfig(BaseModel):
    duration_ms: int = Field(default=800, ge=100, le=300000)
    max_retries: int = Field(default=0, ge=0, le=10)
    fail_first_n: int = Field(default=0, ge=0, le=10)
    backoff_seconds: float = Field(default=1.0, ge=0, le=3600)
    delay_seconds: float = Field(default=0.0, ge=0, le=3600)
    priority: int = Field(default=0, ge=0, le=100)

    model_config = {"extra": "allow"}

    @model_validator(mode="after")
    def validate_retry_bounds(self) -> "TaskConfig":
        if self.fail_first_n > self.max_retries + 1:
            raise ValueError("fail_first_n cannot exceed max_retries + 1.")
        return self


class WorkflowTaskCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    dependencies: list[str] = Field(default_factory=list)
    config: TaskConfig = Field(default_factory=TaskConfig)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Task name cannot be blank.")
        return normalized

    @field_validator("dependencies")
    @classmethod
    def normalize_dependencies(cls, value: list[str]) -> list[str]:
        cleaned = []
        for item in value:
            dependency = item.strip()
            if not dependency:
                continue
            if dependency not in cleaned:
                cleaned.append(dependency)
        return cleaned


class WorkflowCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    tasks: list[WorkflowTaskCreate]

    @field_validator("name")
    @classmethod
    def normalize_workflow_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Workflow name cannot be blank.")
        return normalized

    @field_validator("tasks")
    @classmethod
    def validate_tasks(cls, value: list[WorkflowTaskCreate]) -> list[WorkflowTaskCreate]:
        if not value:
            raise ValueError("Workflow must include at least one task.")
        return value


class WorkflowTaskResponse(BaseModel):
    id: str
    name: str
    dependencies: list[str]
    config: dict[str, Any]

    model_config = {"from_attributes": True}


class WorkflowResponse(BaseModel):
    id: str
    name: str
    created_at: datetime
    tasks: list[WorkflowTaskResponse]

    model_config = {"from_attributes": True}


class ExecutionResponse(BaseModel):
    id: str
    workflow_id: str
    status: ExecutionStatus
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    model_config = {"from_attributes": True}


class ExecutionTaskResponse(BaseModel):
    id: str
    execution_id: str
    task_id: str
    task_name: str
    dependencies: list[str] = Field(default_factory=list)
    status: TaskState
    retries: int
    started_at: datetime | None
    finished_at: datetime | None
    error_message: str | None
    worker_id: str | None


class ExecutionLogResponse(BaseModel):
    id: str
    execution_id: str
    task_id: str | None
    level: str
    message: str
    created_at: datetime

    model_config = {"from_attributes": True}


class QueueStatusResponse(BaseModel):
    queued_jobs: int
    delayed_jobs: int
    in_flight_jobs: int
    total_enqueued: int
    total_processed: int
    queue_backend: str
    is_durable: bool


class WorkerStatusResponse(BaseModel):
    worker_id: str
    state: str
    current_execution_id: str | None
    current_task_id: str | None
    processed_jobs: int
    failed_jobs: int = 0
    last_seen_at: datetime | None
    last_error: str | None = None


class SystemSnapshotResponse(BaseModel):
    queue: QueueStatusResponse
    workers: list[WorkerStatusResponse]


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    environment: str
    timestamp: datetime


class ReadinessResponse(HealthResponse):
    database: str
    workers: str
    queue: QueueStatusResponse
