from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class AuditLogResponse(BaseModel):
    id: str
    actor_label: str
    action: str
    resource_type: str
    resource_id: str
    details: dict[str, Any]
    created_at: datetime

    model_config = {"from_attributes": True}


class SecretCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120, pattern="^[A-Za-z0-9_.-]+$")
    value: str = Field(min_length=1, max_length=8000)


class SecretResponse(BaseModel):
    id: str
    name: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class WebhookCreate(BaseModel):
    url: str = Field(min_length=1, max_length=2048)
    secret: str = Field(min_length=16, max_length=255)
    events: list[str] = Field(default_factory=lambda: ["execution.succeeded", "execution.failed"])
    is_active: bool = True

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        if not value.startswith(("http://", "https://")):
            raise ValueError("Webhook URL must use http or https.")
        return value

    @field_validator("events")
    @classmethod
    def validate_events(cls, value: list[str]) -> list[str]:
        allowed = {
            "execution.succeeded",
            "execution.failed",
            "execution.cancelled",
            "execution.started",
        }
        unknown = sorted(set(value) - allowed)
        if unknown:
            raise ValueError(f"Unsupported events: {', '.join(unknown)}.")
        return sorted(set(value))


class WebhookResponse(BaseModel):
    id: str
    url: str
    events: list[str]
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class WebhookDeliveryResponse(BaseModel):
    id: str
    endpoint_id: str
    event_type: str
    status: str
    attempts: int
    next_attempt_at: datetime
    last_error: str | None
    created_at: datetime
    delivered_at: datetime | None

    model_config = {"from_attributes": True}


class DeadLetterJobResponse(BaseModel):
    id: str
    execution_id: str
    execution_task_id: str
    task_id: str
    attempts: int
    last_error: str | None
    created_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class DeadLetterListResponse(BaseModel):
    items: list[DeadLetterJobResponse]
    total: int


class DiagnosticsResponse(BaseModel):
    version: str
    environment: str
    queue: dict[str, Any]
    workers: list[dict[str, Any]]
    dead_letters: int
    stale_leases: int
    handlers: list[str]
    scheduler: dict[str, Any]
    websockets: int
    config: dict[str, Any]
