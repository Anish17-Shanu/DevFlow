from datetime import datetime

from pydantic import BaseModel, Field


class MeResponse(BaseModel):
    tenant_id: str
    tenant_name: str
    key_id: str
    key_name: str
    role: str


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    role: str = Field(default="viewer", pattern="^(viewer|operator|admin)$")


class ApiKeyResponse(BaseModel):
    id: str
    name: str
    prefix: str
    role: str
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None

    model_config = {"from_attributes": True}


class ApiKeyCreatedResponse(ApiKeyResponse):
    key: str
