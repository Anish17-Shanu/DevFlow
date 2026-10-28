from typing import Any

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    code: str
    message: str
    request_id: str
    details: Any = None


class Page(BaseModel):
    total: int
    limit: int
    offset: int

    model_config = {"extra": "allow"}
