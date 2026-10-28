from fastapi import HTTPException

from backend.core.security import ApiError, Principal
from backend.repositories.execution_repository import ExecutionRepository
from backend.services.audit_service import AuditService
from backend.services.dag_service import DagValidationError


class ExecutionController:
    def __init__(self, session, execution_service=None):
        self.session = session
        self.execution_service = execution_service
        self.repository = ExecutionRepository(session)

    async def run_workflow(self, principal: Principal, workflow_id: str, idempotency_key: str | None):
        try:
            execution = await self.execution_service.trigger_workflow(
                self.session,
                principal.tenant_id,
                workflow_id,
                actor=f"{principal.key_name} ({principal.role})",
                idempotency_key=idempotency_key,
            )
        except DagValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        AuditService.write(
            self.session,
            principal,
            "execution.started",
            "execution",
            execution.id,
            {"workflow_id": workflow_id, "idempotency": bool(idempotency_key)},
        )
        await self.session.commit()
        return execution

    async def list_executions(
        self,
        principal: Principal,
        limit: int,
        offset: int,
        status: str | None,
        workflow_id: str | None,
    ):
        items, total = await self.repository.list_executions(
            principal.tenant_id, limit=limit, offset=offset, status=status, workflow_id=workflow_id
        )
        return {"items": items, "total": total, "limit": limit, "offset": offset}

    async def get_execution(self, principal: Principal, execution_id: str):
        execution = await self.repository.get_execution(principal.tenant_id, execution_id)
        if not execution:
            raise ApiError(404, "not_found", "Execution not found.")
        return execution

    async def get_tasks(self, principal: Principal, execution_id: str):
        if not await self.repository.execution_exists(principal.tenant_id, execution_id):
            raise ApiError(404, "not_found", "Execution not found.")
        return await self.repository.list_execution_tasks(principal.tenant_id, execution_id)

    async def get_logs(self, principal: Principal, execution_id: str, limit: int, offset: int, after: str | None):
        if not await self.repository.execution_exists(principal.tenant_id, execution_id):
            raise ApiError(404, "not_found", "Execution not found.")
        return await self.repository.list_logs(
            principal.tenant_id, execution_id, limit=limit, offset=offset, after=after
        )

    async def cancel(self, principal: Principal, execution_id: str):
        execution = await self.execution_service.cancel_execution(
            self.session,
            principal.tenant_id,
            execution_id,
            actor=f"{principal.key_name} ({principal.role})",
        )
        AuditService.write(self.session, principal, "execution.cancelled", "execution", execution_id)
        await self.session.commit()
        return execution

    async def retry_execution(self, principal: Principal, execution_id: str):
        execution = await self.execution_service.retry_execution(
            self.session,
            principal.tenant_id,
            execution_id,
            actor=f"{principal.key_name} ({principal.role})",
        )
        AuditService.write(
            self.session,
            principal,
            "execution.retried",
            "execution",
            execution.id,
            {"source_execution": execution_id},
        )
        await self.session.commit()
        return execution

    async def retry_task(self, principal: Principal, execution_id: str, task_identifier: str):
        execution = await self.execution_service.retry_task(
            self.session,
            principal.tenant_id,
            execution_id,
            task_identifier,
            actor=f"{principal.key_name} ({principal.role})",
        )
        AuditService.write(
            self.session,
            principal,
            "task.retried",
            "execution",
            execution_id,
            {"task": task_identifier},
        )
        await self.session.commit()
        return execution

    async def skip_task(self, principal: Principal, execution_id: str, task_identifier: str):
        execution = await self.execution_service.skip_task(
            self.session,
            principal.tenant_id,
            execution_id,
            task_identifier,
            actor=f"{principal.key_name} ({principal.role})",
        )
        AuditService.write(
            self.session,
            principal,
            "task.skipped",
            "execution",
            execution_id,
            {"task": task_identifier},
        )
        await self.session.commit()
        return execution
