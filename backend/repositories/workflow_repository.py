from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.models.entities import Workflow


class WorkflowRepository:
    def __init__(self, session):
        self.session = session

    async def list_workflows(self) -> list[Workflow]:
        result = await self.session.execute(
            select(Workflow).options(selectinload(Workflow.tasks)).order_by(Workflow.created_at.desc())
        )
        return list(result.scalars().unique())

    async def get_workflow(self, workflow_id: str) -> Workflow | None:
        result = await self.session.execute(
            select(Workflow).where(Workflow.id == workflow_id).options(selectinload(Workflow.tasks))
        )
        return result.scalars().unique().first()
