from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.dependencies import require_role
from backend.controllers.ops_controller import OpsController
from backend.controllers.workflow_controller import WorkflowController
from backend.core.database import get_db_session
from backend.core.security import Principal
from backend.sample_data.templates import TEMPLATE_WORKFLOWS
from backend.schemas.workflow import (
    ScheduleCreate,
    ScheduleResponse,
    WorkflowCloneRequest,
    WorkflowCreate,
    WorkflowListResponse,
    WorkflowResponse,
    WorkflowRevisionResponse,
    WorkflowTemplateResponse,
    WorkflowUpdate,
)

router = APIRouter(prefix="/workflows", tags=["workflows"])


@router.get("/templates", response_model=list[WorkflowTemplateResponse])
async def list_templates(principal: Principal = Depends(require_role("viewer"))):
    return TEMPLATE_WORKFLOWS


@router.post("/import", response_model=WorkflowResponse, status_code=201)
async def import_workflow(
    payload: WorkflowCreate,
    principal: Principal = Depends(require_role("operator")),
    session: AsyncSession = Depends(get_db_session),
):
    controller = WorkflowController(session)
    return await controller.import_workflow(principal, payload)


@router.post("", response_model=WorkflowResponse, status_code=201)
async def create_workflow(
    payload: WorkflowCreate,
    principal: Principal = Depends(require_role("operator")),
    session: AsyncSession = Depends(get_db_session),
):
    controller = WorkflowController(session)
    return await controller.create(principal, payload)


@router.get("", response_model=WorkflowListResponse)
async def list_workflows(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    include_archived: bool = Query(default=False),
    principal: Principal = Depends(require_role("viewer")),
    session: AsyncSession = Depends(get_db_session),
):
    controller = WorkflowController(session)
    return await controller.list(principal, limit, offset, include_archived)


@router.get("/{workflow_id}", response_model=WorkflowResponse)
async def get_workflow(
    workflow_id: str,
    principal: Principal = Depends(require_role("viewer")),
    session: AsyncSession = Depends(get_db_session),
):
    controller = WorkflowController(session)
    return await controller.get(principal, workflow_id)


@router.patch("/{workflow_id}", response_model=WorkflowResponse)
async def update_workflow(
    workflow_id: str,
    payload: WorkflowUpdate,
    principal: Principal = Depends(require_role("operator")),
    session: AsyncSession = Depends(get_db_session),
):
    controller = WorkflowController(session)
    return await controller.update(principal, workflow_id, payload)


@router.delete("/{workflow_id}", status_code=204)
async def delete_workflow(
    workflow_id: str,
    principal: Principal = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_db_session),
):
    controller = WorkflowController(session)
    await controller.delete(principal, workflow_id)
    return Response(status_code=204)


@router.post("/{workflow_id}/clone", response_model=WorkflowResponse, status_code=201)
async def clone_workflow(
    workflow_id: str,
    payload: WorkflowCloneRequest,
    principal: Principal = Depends(require_role("operator")),
    session: AsyncSession = Depends(get_db_session),
):
    controller = WorkflowController(session)
    return await controller.clone(principal, workflow_id, payload.name)


@router.get("/{workflow_id}/revisions", response_model=list[WorkflowRevisionResponse])
async def list_revisions(
    workflow_id: str,
    principal: Principal = Depends(require_role("viewer")),
    session: AsyncSession = Depends(get_db_session),
):
    controller = WorkflowController(session)
    return await controller.revisions(principal, workflow_id)


@router.get("/{workflow_id}/export")
async def export_workflow(
    workflow_id: str,
    principal: Principal = Depends(require_role("viewer")),
    session: AsyncSession = Depends(get_db_session),
):
    controller = WorkflowController(session)
    return await controller.export(principal, workflow_id)


@router.get("/{workflow_id}/schedules", response_model=list[ScheduleResponse])
async def list_schedules(
    workflow_id: str,
    principal: Principal = Depends(require_role("viewer")),
    session: AsyncSession = Depends(get_db_session),
):
    controller = OpsController(session)
    return await controller.list_schedules(principal, workflow_id)


@router.post("/{workflow_id}/schedules", response_model=ScheduleResponse, status_code=201)
async def create_schedule(
    workflow_id: str,
    payload: ScheduleCreate,
    principal: Principal = Depends(require_role("operator")),
    session: AsyncSession = Depends(get_db_session),
):
    controller = OpsController(session)
    return await controller.create_schedule(principal, workflow_id, payload)
