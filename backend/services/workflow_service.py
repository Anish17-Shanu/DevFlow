from sqlalchemy.exc import NoResultFound

from backend.models.entities import TaskDefinition, Workflow
from backend.repositories.workflow_repository import WorkflowRepository
from backend.schemas.workflow import WorkflowCreate
from backend.services.dag_service import DagService


class WorkflowService:
    def __init__(self, session):
        self.session = session
        self.repository = WorkflowRepository(session)

    async def create_workflow(self, payload: WorkflowCreate) -> Workflow:
        task_dicts = [task.model_dump() for task in payload.tasks]
        DagService.validate(task_dicts)

        workflow = Workflow(name=payload.name)
        self.session.add(workflow)
        await self.session.flush()

        for task in task_dicts:
            self.session.add(
                TaskDefinition(
                    workflow_id=workflow.id,
                    name=task["name"],
                    dependencies=task["dependencies"],
                    config=task["config"],
                )
            )

        await self.session.commit()
        workflow = await self.repository.get_workflow(workflow.id)
        if not workflow:
            raise NoResultFound("Workflow not found after creation.")
        return workflow

    async def list_workflows(self) -> list[Workflow]:
        return await self.repository.list_workflows()

    async def get_workflow(self, workflow_id: str) -> Workflow | None:
        return await self.repository.get_workflow(workflow_id)
