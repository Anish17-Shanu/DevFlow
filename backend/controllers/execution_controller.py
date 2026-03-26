from fastapi import HTTPException

from backend.repositories.execution_repository import ExecutionRepository


class ExecutionController:
    def __init__(self, session, execution_service):
        self.session = session
        self.execution_service = execution_service
        self.repository = ExecutionRepository(session)

    async def run_workflow(self, workflow_id: str):
        try:
            return await self.execution_service.trigger_workflow(self.session, workflow_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    async def get_execution(self, execution_id: str):
        execution = await self.repository.get_execution(execution_id)
        if not execution:
            raise HTTPException(status_code=404, detail="Execution not found.")
        return execution

    async def get_tasks(self, execution_id: str):
        execution = await self.repository.get_execution(execution_id)
        if not execution:
            raise HTTPException(status_code=404, detail="Execution not found.")
        return await self.repository.list_execution_tasks(execution_id)

    async def get_logs(self, execution_id: str):
        execution = await self.repository.get_execution(execution_id)
        if not execution:
            raise HTTPException(status_code=404, detail="Execution not found.")
        return await self.repository.list_logs(execution_id)
