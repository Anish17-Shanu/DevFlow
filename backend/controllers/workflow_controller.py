from backend.core.security import ApiError, Principal
from backend.schemas.workflow import WorkflowCreate, WorkflowUpdate
from backend.services.audit_service import AuditService
from backend.services.dag_service import DagValidationError
from backend.services.workflow_service import WorkflowService


class WorkflowController:
    def __init__(self, session):
        self.session = session
        self.service = WorkflowService(session)

    async def create(self, principal: Principal, payload: WorkflowCreate):
        try:
            workflow = await self.service.create_workflow(
                principal.tenant_id, payload, actor=f"{principal.key_name} ({principal.role})"
            )
        except DagValidationError as exc:
            raise ApiError(400, "invalid_dag", str(exc)) from exc
        AuditService.write(
            self.session, principal, "workflow.created", "workflow", workflow.id, {"name": workflow.name}
        )
        await self.session.commit()
        return workflow

    async def list(self, principal: Principal, limit: int, offset: int, include_archived: bool):
        items, total = await self.service.list_workflows(
            principal.tenant_id, limit=limit, offset=offset, include_archived=include_archived
        )
        return {"items": items, "total": total, "limit": limit, "offset": offset}

    async def get(self, principal: Principal, workflow_id: str):
        workflow = await self.service.get_workflow(principal.tenant_id, workflow_id)
        if not workflow:
            raise ApiError(404, "not_found", "Workflow not found.")
        return workflow

    async def update(self, principal: Principal, workflow_id: str, payload: WorkflowUpdate):
        try:
            workflow = await self.service.update_workflow(
                principal.tenant_id, workflow_id, payload, actor=f"{principal.key_name} ({principal.role})"
            )
        except DagValidationError as exc:
            raise ApiError(400, "invalid_dag", str(exc)) from exc
        AuditService.write(
            self.session,
            principal,
            "workflow.updated",
            "workflow",
            workflow.id,
            {"revision": workflow.current_revision},
        )
        await self.session.commit()
        return workflow

    async def delete(self, principal: Principal, workflow_id: str):
        await self.service.archive_workflow(principal.tenant_id, workflow_id)
        AuditService.write(self.session, principal, "workflow.archived", "workflow", workflow_id)
        await self.session.commit()

    async def clone(self, principal: Principal, workflow_id: str, name: str | None):
        workflow = await self.service.clone_workflow(
            principal.tenant_id, workflow_id, name, actor=f"{principal.key_name} ({principal.role})"
        )
        AuditService.write(
            self.session,
            principal,
            "workflow.cloned",
            "workflow",
            workflow.id,
            {"source": workflow_id},
        )
        await self.session.commit()
        return workflow

    async def revisions(self, principal: Principal, workflow_id: str):
        return await self.service.list_revisions(principal.tenant_id, workflow_id)

    async def export(self, principal: Principal, workflow_id: str):
        return await self.service.export_workflow(principal.tenant_id, workflow_id)

    async def import_workflow(self, principal: Principal, payload: WorkflowCreate):
        return await self.create(principal, payload)
