from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from backend.models.entities import ExecutionStatus, TaskState


class TaskConfig(BaseModel):
    type: Literal["sleep", "http", "echo"] = "sleep"
    duration_ms: int = Field(default=800, ge=100, le=300000)
    max_retries: int = Field(default=0, ge=0, le=10)
    fail_first_n: int = Field(default=0, ge=0, le=10)
    backoff_seconds: float = Field(default=1.0, ge=0, le=3600)
    delay_seconds: float = Field(default=0.0, ge=0, le=3600)
    priority: int = Field(default=0, ge=0, le=100)
    timeout_seconds: int = Field(default=60, ge=1, le=86400)
    allow_failure: bool = False

    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"] = "GET"
    url: str | None = Field(default=None, max_length=2048)
    headers: dict[str, str] = Field(default_factory=dict)
    body: str | None = Field(default=None, max_length=20000)
    expected_status: int | None = Field(default=None, ge=100, le=599)
    message: str | None = Field(default=None, max_length=2000)

    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def validate_retry_bounds(self) -> "TaskConfig":
        if self.fail_first_n > self.max_retries + 1:
            raise ValueError("fail_first_n cannot exceed max_retries + 1.")
        if self.type == "http" and not self.url:
            raise ValueError("HTTP tasks require a url.")
        if len(self.headers) > 20:
            raise ValueError("A task can define at most 20 headers.")
        return self

    @field_validator("headers")
    @classmethod
    def validate_headers(cls, value: dict[str, str]) -> dict[str, str]:
        for name, header_value in value.items():
            if any(character in name + header_value for character in ("\r", "\n")):
                raise ValueError("Header names and values cannot contain newlines.")
        return value


class WorkflowTaskCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    dependencies: list[str] = Field(default_factory=list, max_length=100)
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
    description: str | None = Field(default=None, max_length=2000)
    tasks: list[WorkflowTaskCreate] = Field(max_length=200)

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


class WorkflowUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    tasks: list[WorkflowTaskCreate] | None = Field(default=None, max_length=200)

    @field_validator("name")
    @classmethod
    def normalize_optional_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("Workflow name cannot be blank.")
        return normalized

    @field_validator("tasks")
    @classmethod
    def validate_optional_tasks(cls, value: list[WorkflowTaskCreate] | None) -> list[WorkflowTaskCreate] | None:
        if value is not None and not value:
            raise ValueError("Workflow must include at least one task.")
        return value


class WorkflowCloneRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)


class WorkflowTemplateResponse(BaseModel):
    name: str
    description: str | None = None
    tasks: list[WorkflowTaskCreate]


class WorkflowTaskResponse(BaseModel):
    id: str
    name: str
    dependencies: list[str]
    config: dict[str, Any]

    model_config = {"from_attributes": True}


class WorkflowResponse(BaseModel):
    id: str
    name: str
    description: str | None = None
    current_revision: int = 1
    is_archived: bool = False
    created_at: datetime
    updated_at: datetime | None = None
    tasks: list[WorkflowTaskResponse]

    model_config = {"from_attributes": True}


class WorkflowListResponse(BaseModel):
    items: list[WorkflowResponse]
    total: int
    limit: int
    offset: int


class WorkflowRevisionResponse(BaseModel):
    id: str
    revision: int
    document: dict[str, Any]
    created_by: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ExecutionResponse(BaseModel):
    id: str
    workflow_id: str
    workflow_name: str = ""
    revision: int = 1
    status: ExecutionStatus
    cancellation_requested: bool = False
    triggered_by: str = "system"
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class ExecutionListResponse(BaseModel):
    items: list[ExecutionResponse]
    total: int
    limit: int
    offset: int


class ExecutionTaskResponse(BaseModel):
    id: str
    execution_id: str
    task_id: str | None
    task_name: str
    dependencies: list[str] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)
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


class ExecutionLogListResponse(BaseModel):
    items: list[ExecutionLogResponse]
    next_cursor: str | None = None


class QueueStatusResponse(BaseModel):
    queued_jobs: int
    delayed_jobs: int
    in_flight_jobs: int
    dead_letter_jobs: int = 0
    total_enqueued: int
    total_processed: int
    queue_backend: str
    is_durable: bool
    healthy: bool = True
    error: str | None = None


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


class ScheduleCreate(BaseModel):
    cron: str | None = Field(default=None, max_length=120)
    interval_seconds: int | None = Field(default=None, ge=10, le=31_536_000)

    @model_validator(mode="after")
    def validate_trigger(self) -> "ScheduleCreate":
        if not self.cron and not self.interval_seconds:
            raise ValueError("Provide either a cron expression or an interval.")
        if self.cron:
            from croniter import croniter

            if not croniter.is_valid(self.cron):
                raise ValueError("Invalid cron expression.")
        return self


class ScheduleResponse(BaseModel):
    id: str
    workflow_id: str
    cron: str | None
    interval_seconds: int | None
    next_run_at: datetime
    is_enabled: bool
    created_at: datetime
    last_run_at: datetime | None

    model_config = {"from_attributes": True}
