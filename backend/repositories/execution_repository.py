from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.models.entities import Execution, ExecutionLog, ExecutionTask, Workflow


class ExecutionRepository:
    def __init__(self, session):
        self.session = session

    async def get_execution(self, execution_id: str) -> Execution | None:
        result = await self.session.execute(
            select(Execution)
            .where(Execution.id == execution_id)
            .options(
                selectinload(Execution.workflow).selectinload(Workflow.tasks),
                selectinload(Execution.execution_tasks).selectinload(ExecutionTask.task),
                selectinload(Execution.logs),
            )
        )
        return result.scalars().unique().first()

    async def list_execution_tasks(self, execution_id: str) -> list[ExecutionTask]:
        result = await self.session.execute(
            select(ExecutionTask)
            .where(ExecutionTask.execution_id == execution_id)
            .options(selectinload(ExecutionTask.task))
        )
        return list(result.scalars().unique())

    async def list_logs(self, execution_id: str) -> list[ExecutionLog]:
        result = await self.session.execute(
            select(ExecutionLog)
            .where(ExecutionLog.execution_id == execution_id)
            .order_by(ExecutionLog.created_at.asc())
        )
        return list(result.scalars())
