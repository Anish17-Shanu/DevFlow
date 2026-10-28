from __future__ import annotations

from typing import Any

from backend.models.entities import OutboxEvent


class OutboxService:
    @staticmethod
    def write(
        session,
        tenant_id: str,
        event_type: str,
        execution_id: str | None,
        payload: dict[str, Any] | None = None,
    ) -> OutboxEvent:
        event = OutboxEvent(
            tenant_id=tenant_id,
            event_type=event_type,
            execution_id=execution_id,
            payload=payload or {},
        )
        session.add(event)
        return event
