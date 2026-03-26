from datetime import datetime

from pydantic import BaseModel, Field

from backend.models.entities import ExecutionStatus, TaskState


class WorkflowTaskCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    dependencies: list[str] = Field(default_factory=list)
    config: dict = Field(default_factory=dict)


class WorkflowCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    tasks: list[WorkflowTaskCreate]


class WorkflowTaskResponse(BaseModel):
    id: str
    name: str
    dependencies: list[str]
    config: dict

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


class WorkerStatusResponse(BaseModel):
    worker_id: str
    state: str
    current_execution_id: str | None
    current_task_id: str | None
    processed_jobs: int
    last_seen_at: datetime | None


class SystemSnapshotResponse(BaseModel):
    queue: QueueStatusResponse
    workers: list[WorkerStatusResponse]
