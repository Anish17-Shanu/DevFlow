from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from backend.services.secret_service import SecretService


class HandlerError(Exception):
    """Raised when a task handler cannot complete the work."""


@dataclass
class HandlerContext:
    tenant_id: str
    execution_id: str
    task_name: str
    config: dict[str, Any]
    secrets: SecretService
    attempt: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    async def resolve_secret(self, name: str) -> str:
        return await self.secrets.resolve(self.tenant_id, name)


Handler = Callable[[HandlerContext], Awaitable[dict[str, Any] | None]]
