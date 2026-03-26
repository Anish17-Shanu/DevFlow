from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.controllers.workflow_controller import WorkflowController
from backend.core.database import get_db_session
from backend.schemas.workflow import WorkflowCreate, WorkflowResponse


router = APIRouter(prefix="/workflows", tags=["workflows"])


@router.post("", response_model=WorkflowResponse)
async def create_workflow(
    payload: WorkflowCreate,
    session: AsyncSession = Depends(get_db_session),
):
    controller = WorkflowController(session)
    return await controller.create(payload)


@router.get("", response_model=list[WorkflowResponse])
async def list_workflows(session: AsyncSession = Depends(get_db_session)):
    controller = WorkflowController(session)
    return await controller.list()


@router.get("/{workflow_id}", response_model=WorkflowResponse)
async def get_workflow(workflow_id: str, session: AsyncSession = Depends(get_db_session)):
    controller = WorkflowController(session)
    return await controller.get(workflow_id)
