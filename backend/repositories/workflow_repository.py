from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from backend.models.entities import Workflow, WorkflowRevision


class WorkflowRepository:
    def __init__(self, session):
        self.session = session

    async def list_workflows(
        self, tenant_id: str, limit: int, offset: int, include_archived: bool = False
    ) -> tuple[list[Workflow], int]:
        conditions = [Workflow.tenant_id == tenant_id]
        if not include_archived:
            conditions.append(Workflow.is_archived.is_(False))
        total = await self.session.scalar(select(func.count()).select_from(Workflow).where(*conditions))
        result = await self.session.execute(
            select(Workflow)
            .where(*conditions)
            .options(selectinload(Workflow.tasks))
            .order_by(Workflow.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().unique()), int(total or 0)

    async def get_workflow(self, tenant_id: str, workflow_id: str, include_archived: bool = True) -> Workflow | None:
        conditions = [Workflow.id == workflow_id, Workflow.tenant_id == tenant_id]
        if not include_archived:
            conditions.append(Workflow.is_archived.is_(False))
        result = await self.session.execute(
            select(Workflow)
            .where(*conditions)
            .options(selectinload(Workflow.tasks))
            .execution_options(populate_existing=True)
        )
        return result.scalars().unique().first()

    async def get_latest_revision(self, workflow_id: str) -> WorkflowRevision | None:
        result = await self.session.execute(
            select(WorkflowRevision)
            .where(WorkflowRevision.workflow_id == workflow_id)
            .order_by(WorkflowRevision.revision.desc())
            .limit(1)
        )
        return result.scalars().first()

    async def list_revisions(self, workflow_id: str) -> list[WorkflowRevision]:
        result = await self.session.execute(
            select(WorkflowRevision)
            .where(WorkflowRevision.workflow_id == workflow_id)
            .order_by(WorkflowRevision.revision.desc())
        )
        return list(result.scalars())

    async def name_exists(self, tenant_id: str, name: str, exclude_id: str | None = None) -> bool:
        conditions = [Workflow.tenant_id == tenant_id, Workflow.name == name]
        if exclude_id:
            conditions.append(Workflow.id != exclude_id)
        return bool(await self.session.scalar(select(Workflow.id).where(*conditions).limit(1)))
