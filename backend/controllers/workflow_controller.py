from fastapi import HTTPException

from backend.schemas.workflow import WorkflowCreate
from backend.services.workflow_service import WorkflowService


class WorkflowController:
    def __init__(self, session):
        self.service = WorkflowService(session)

    async def create(self, payload: WorkflowCreate):
        try:
            return await self.service.create_workflow(payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    async def list(self):
        return await self.service.list_workflows()

    async def get(self, workflow_id: str):
        workflow = await self.service.get_workflow(workflow_id)
        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found.")
        return workflow
