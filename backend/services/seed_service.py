from sqlalchemy import func, select

from backend.models.entities import Workflow
from backend.sample_data.workflows import SAMPLE_WORKFLOWS
from backend.schemas.workflow import WorkflowCreate
from backend.services.workflow_service import WorkflowService


class SeedService:
    @staticmethod
    async def seed_default_workflows(session) -> None:
        count = await session.scalar(select(func.count()).select_from(Workflow))
        if count and count > 0:
            return

        service = WorkflowService(session)
        for workflow in SAMPLE_WORKFLOWS:
            await service.create_workflow(WorkflowCreate(**workflow))
