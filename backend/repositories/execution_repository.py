from __future__ import annotations

import base64
from datetime import datetime

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import selectinload

from backend.models.entities import Execution, ExecutionLog, ExecutionTask


def encode_cursor(created_at: datetime, log_id: str) -> str:
    raw = f"{created_at.isoformat()}|{log_id}".encode()
    return base64.urlsafe_b64encode(raw).decode("ascii")


def decode_cursor(cursor: str) -> tuple[datetime, str] | None:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
        timestamp, log_id = raw.split("|", 1)
        return datetime.fromisoformat(timestamp), log_id
    except Exception:
        return None


class ExecutionRepository:
    def __init__(self, session):
        self.session = session

    async def execution_exists(self, tenant_id: str, execution_id: str) -> bool:
        result = await self.session.scalar(
            select(Execution.id).where(Execution.id == execution_id, Execution.tenant_id == tenant_id)
        )
        return result is not None

    async def get_execution(self, tenant_id: str, execution_id: str) -> Execution | None:
        result = await self.session.execute(
            select(Execution)
            .where(Execution.id == execution_id, Execution.tenant_id == tenant_id)
            .options(selectinload(Execution.execution_tasks))
        )
        return result.scalars().unique().first()

    async def list_executions(
        self,
        tenant_id: str,
        limit: int,
        offset: int,
        status: str | None = None,
        workflow_id: str | None = None,
    ) -> tuple[list[Execution], int]:
        conditions = [Execution.tenant_id == tenant_id]
        if status:
            conditions.append(Execution.status == status)
        if workflow_id:
            conditions.append(Execution.workflow_id == workflow_id)
        total = await self.session.scalar(select(func.count()).select_from(Execution).where(*conditions))
        result = await self.session.execute(
            select(Execution).where(*conditions).order_by(Execution.created_at.desc()).limit(limit).offset(offset)
        )
        return list(result.scalars()), int(total or 0)

    async def list_execution_tasks(self, tenant_id: str, execution_id: str) -> list[ExecutionTask]:
        result = await self.session.execute(
            select(ExecutionTask)
            .join(Execution, Execution.id == ExecutionTask.execution_id)
            .where(ExecutionTask.execution_id == execution_id, Execution.tenant_id == tenant_id)
            .order_by(ExecutionTask.started_at.asc().nulls_first(), ExecutionTask.task_name.asc())
        )
        return list(result.scalars().unique())

    async def list_logs(
        self,
        tenant_id: str,
        execution_id: str,
        limit: int,
        offset: int = 0,
        after: str | None = None,
    ) -> tuple[list[ExecutionLog], str | None]:
        conditions = [ExecutionLog.execution_id == execution_id, Execution.tenant_id == tenant_id]
        if after:
            decoded = decode_cursor(after)
            if decoded is not None:
                timestamp, log_id = decoded
                conditions.append(
                    or_(
                        ExecutionLog.created_at > timestamp,
                        and_(ExecutionLog.created_at == timestamp, ExecutionLog.id > log_id),
                    )
                )
        result = await self.session.execute(
            select(ExecutionLog)
            .join(Execution, Execution.id == ExecutionLog.execution_id)
            .where(*conditions)
            .order_by(ExecutionLog.created_at.asc(), ExecutionLog.id.asc())
            .limit(limit + 1)
            .offset(offset if not after else 0)
        )
        rows = list(result.scalars())
        next_cursor = None
        if len(rows) > limit:
            rows = rows[:limit]
            last = rows[-1]
            next_cursor = encode_cursor(last.created_at, last.id)
        return rows, next_cursor
