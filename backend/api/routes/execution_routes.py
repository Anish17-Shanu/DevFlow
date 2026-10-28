from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.dependencies import get_execution_service, require_role
from backend.controllers.execution_controller import ExecutionController
from backend.core.database import get_db_session
from backend.core.security import Principal
from backend.schemas.workflow import (
    ExecutionListResponse,
    ExecutionLogListResponse,
    ExecutionResponse,
    ExecutionTaskResponse,
)

router = APIRouter(tags=["executions"])


def _task_response(task) -> ExecutionTaskResponse:
    return ExecutionTaskResponse(
        id=task.id,
        execution_id=task.execution_id,
        task_id=task.task_id,
        task_name=task.task_name,
        dependencies=task.dependencies or [],
        config=task.config or {},
        status=task.status,
        retries=task.retries,
        started_at=task.started_at,
        finished_at=task.finished_at,
        error_message=task.error_message,
        worker_id=task.worker_id,
    )


@router.post("/workflows/{workflow_id}/run", response_model=ExecutionResponse)
async def run_workflow(
    workflow_id: str,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    principal: Principal = Depends(require_role("operator")),
    session: AsyncSession = Depends(get_db_session),
    execution_service=Depends(get_execution_service),
):
    controller = ExecutionController(session, execution_service)
    return await controller.run_workflow(principal, workflow_id, idempotency_key)


@router.get("/executions", response_model=ExecutionListResponse)
async def list_executions(
    limit: int = Query(default=25, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    status: str | None = Query(default=None, pattern="^(pending|running|success|failed|cancelled)$"),
    workflow_id: str | None = Query(default=None, max_length=36),
    principal: Principal = Depends(require_role("viewer")),
    session: AsyncSession = Depends(get_db_session),
):
    controller = ExecutionController(session)
    return await controller.list_executions(principal, limit, offset, status, workflow_id)


@router.get("/executions/{execution_id}", response_model=ExecutionResponse)
async def get_execution(
    execution_id: str,
    principal: Principal = Depends(require_role("viewer")),
    session: AsyncSession = Depends(get_db_session),
):
    controller = ExecutionController(session)
    return await controller.get_execution(principal, execution_id)


@router.get("/executions/{execution_id}/tasks", response_model=list[ExecutionTaskResponse])
async def get_execution_tasks(
    execution_id: str,
    principal: Principal = Depends(require_role("viewer")),
    session: AsyncSession = Depends(get_db_session),
):
    controller = ExecutionController(session)
    tasks = await controller.get_tasks(principal, execution_id)
    return [_task_response(task) for task in tasks]


@router.get("/executions/{execution_id}/logs", response_model=ExecutionLogListResponse)
async def get_execution_logs(
    execution_id: str,
    limit: int = Query(default=200, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
    after: str | None = Query(default=None, max_length=512),
    principal: Principal = Depends(require_role("viewer")),
    session: AsyncSession = Depends(get_db_session),
):
    controller = ExecutionController(session)
    items, next_cursor = await controller.get_logs(principal, execution_id, limit, offset, after)
    return {"items": items, "next_cursor": next_cursor}


@router.post("/executions/{execution_id}/cancel", response_model=ExecutionResponse)
async def cancel_execution(
    execution_id: str,
    principal: Principal = Depends(require_role("operator")),
    session: AsyncSession = Depends(get_db_session),
    execution_service=Depends(get_execution_service),
):
    controller = ExecutionController(session, execution_service)
    return await controller.cancel(principal, execution_id)


@router.post("/executions/{execution_id}/retry", response_model=ExecutionResponse)
async def retry_execution(
    execution_id: str,
    principal: Principal = Depends(require_role("operator")),
    session: AsyncSession = Depends(get_db_session),
    execution_service=Depends(get_execution_service),
):
    controller = ExecutionController(session, execution_service)
    return await controller.retry_execution(principal, execution_id)


@router.post("/executions/{execution_id}/tasks/{task_identifier}/retry", response_model=ExecutionResponse)
async def retry_task(
    execution_id: str,
    task_identifier: str,
    principal: Principal = Depends(require_role("operator")),
    session: AsyncSession = Depends(get_db_session),
    execution_service=Depends(get_execution_service),
):
    controller = ExecutionController(session, execution_service)
    return await controller.retry_task(principal, execution_id, task_identifier)


@router.post("/executions/{execution_id}/tasks/{task_identifier}/skip", response_model=ExecutionResponse)
async def skip_task(
    execution_id: str,
    task_identifier: str,
    principal: Principal = Depends(require_role("operator")),
    session: AsyncSession = Depends(get_db_session),
    execution_service=Depends(get_execution_service),
):
    controller = ExecutionController(session, execution_service)
    return await controller.skip_task(principal, execution_id, task_identifier)
