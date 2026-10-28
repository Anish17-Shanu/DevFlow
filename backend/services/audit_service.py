from __future__ import annotations

from typing import Any

from backend.core.security import Principal
from backend.models.entities import AuditLog


class AuditService:
    @staticmethod
    def write(
        session,
        principal: Principal | None,
        action: str,
        resource_type: str,
        resource_id: str,
        details: dict[str, Any] | None = None,
        tenant_id: str | None = None,
    ) -> None:
        session.add(
            AuditLog(
                tenant_id=principal.tenant_id if principal else tenant_id or "",
                actor_key_id=principal.key_id if principal else None,
                actor_label=f"{principal.key_name} ({principal.role})" if principal else "system",
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                details=details or {},
            )
        )
