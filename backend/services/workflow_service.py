from __future__ import annotations

from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError

from backend.core.security import ApiError
from backend.core.time import utc_now
from backend.models.entities import TaskDefinition, Workflow, WorkflowRevision
from backend.repositories.workflow_repository import WorkflowRepository
from backend.schemas.workflow import WorkflowCreate, WorkflowUpdate
from backend.services.dag_service import DagService, DagValidationError


class WorkflowService:
    def __init__(self, session):
        self.session = session
        self.repository = WorkflowRepository(session)

    async def create_workflow(
        self,
        tenant_id: str,
        payload: WorkflowCreate,
        actor: str = "system",
        name_override: str | None = None,
    ) -> Workflow:
        name = (name_override or payload.name).strip()
        task_dicts = [task.model_dump() for task in payload.tasks]
        DagService.validate(task_dicts)
        if await self.repository.name_exists(tenant_id, name):
            raise ApiError(409, "conflict", "A workflow with this name already exists.")

        workflow = Workflow(
            tenant_id=tenant_id,
            name=name,
            description=payload.description,
            current_revision=1,
        )
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

        self.session.add(
            WorkflowRevision(
                workflow_id=workflow.id,
                tenant_id=tenant_id,
                revision=1,
                document={
                    "name": name,
                    "description": payload.description,
                    "revision": 1,
                    "tasks": task_dicts,
                },
                created_by=actor,
            )
        )
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ApiError(409, "conflict", "A workflow with this name already exists.") from exc

        workflow = await self.repository.get_workflow(tenant_id, workflow.id)
        if not workflow:
            raise ApiError(500, "internal_error", "Workflow not found after creation.")
        return workflow

    async def update_workflow(
        self,
        tenant_id: str,
        workflow_id: str,
        payload: WorkflowUpdate,
        actor: str = "system",
    ) -> Workflow:
        workflow = await self.repository.get_workflow(tenant_id, workflow_id, include_archived=False)
        if workflow is None:
            raise ApiError(404, "not_found", "Workflow not found.")

        existing_document = (await self.repository.get_latest_revision(workflow.id)).document
        name = payload.name or workflow.name
        description = payload.description if payload.description is not None else workflow.description
        if payload.tasks is not None:
            task_dicts = [task.model_dump() for task in payload.tasks]
            DagService.validate(task_dicts)
        else:
            task_dicts = existing_document.get("tasks", [])

        if name != workflow.name and await self.repository.name_exists(tenant_id, name, exclude_id=workflow.id):
            raise ApiError(409, "conflict", "A workflow with this name already exists.")

        revision_number = workflow.current_revision + 1
        workflow.name = name
        workflow.description = description
        workflow.current_revision = revision_number
        workflow.updated_at = utc_now()

        await self.session.execute(delete(TaskDefinition).where(TaskDefinition.workflow_id == workflow.id))
        for task in task_dicts:
            self.session.add(
                TaskDefinition(
                    workflow_id=workflow.id,
                    name=task["name"],
                    dependencies=task["dependencies"],
                    config=task["config"],
                )
            )

        self.session.add(
            WorkflowRevision(
                workflow_id=workflow.id,
                tenant_id=tenant_id,
                revision=revision_number,
                document={
                    "name": name,
                    "description": description,
                    "revision": revision_number,
                    "tasks": task_dicts,
                },
                created_by=actor,
            )
        )
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ApiError(409, "conflict", "Workflow update conflicted with another change.") from exc
        refreshed = await self.repository.get_workflow(tenant_id, workflow.id)
        if refreshed is None:
            raise ApiError(500, "internal_error", "Workflow disappeared after update.")
        return refreshed

    async def archive_workflow(self, tenant_id: str, workflow_id: str) -> None:
        workflow = await self.repository.get_workflow(tenant_id, workflow_id)
        if workflow is None:
            raise ApiError(404, "not_found", "Workflow not found.")
        workflow.is_archived = True
        workflow.updated_at = utc_now()
        await self.session.commit()

    async def clone_workflow(self, tenant_id: str, workflow_id: str, name: str | None, actor: str) -> Workflow:
        workflow = await self.repository.get_workflow(tenant_id, workflow_id)
        if workflow is None:
            raise ApiError(404, "not_found", "Workflow not found.")
        document = (await self.repository.get_latest_revision(workflow.id)).document
        payload = WorkflowCreate(**document)
        return await self.create_workflow(
            tenant_id,
            payload,
            actor=actor,
            name_override=name or f"{workflow.name} copy",
        )

    async def export_workflow(self, tenant_id: str, workflow_id: str) -> dict:
        workflow = await self.repository.get_workflow(tenant_id, workflow_id)
        if workflow is None:
            raise ApiError(404, "not_found", "Workflow not found.")
        revision = await self.repository.get_latest_revision(workflow.id)
        return revision.document

    async def list_workflows(
        self, tenant_id: str, limit: int = 50, offset: int = 0, include_archived: bool = False
    ) -> tuple[list[Workflow], int]:
        return await self.repository.list_workflows(tenant_id, limit, offset, include_archived)

    async def get_workflow(self, tenant_id: str, workflow_id: str) -> Workflow | None:
        return await self.repository.get_workflow(tenant_id, workflow_id)

    async def list_revisions(self, tenant_id: str, workflow_id: str) -> list[WorkflowRevision]:
        workflow = await self.repository.get_workflow(tenant_id, workflow_id)
        if workflow is None:
            raise ApiError(404, "not_found", "Workflow not found.")
        return await self.repository.list_revisions(workflow.id)


__all__ = ["DagValidationError", "WorkflowService"]
