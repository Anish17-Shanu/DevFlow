from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.dependencies import get_execution_service
from backend.controllers.execution_controller import ExecutionController
from backend.core.database import get_db_session
from backend.schemas.workflow import ExecutionLogResponse, ExecutionResponse, ExecutionTaskResponse


router = APIRouter(tags=["executions"])


@router.post("/workflows/{workflow_id}/run", response_model=ExecutionResponse)
async def run_workflow(
    workflow_id: str,
    session: AsyncSession = Depends(get_db_session),
    execution_service=Depends(get_execution_service),
):
    controller = ExecutionController(session, execution_service)
    return await controller.run_workflow(workflow_id)


@router.get("/executions/{execution_id}", response_model=ExecutionResponse)
async def get_execution(
    execution_id: str,
    session: AsyncSession = Depends(get_db_session),
    execution_service=Depends(get_execution_service),
):
    controller = ExecutionController(session, execution_service)
    return await controller.get_execution(execution_id)


@router.get("/executions/{execution_id}/tasks", response_model=list[ExecutionTaskResponse])
async def get_execution_tasks(
    execution_id: str,
    session: AsyncSession = Depends(get_db_session),
    execution_service=Depends(get_execution_service),
):
    controller = ExecutionController(session, execution_service)
    tasks = await controller.get_tasks(execution_id)
    return [
        ExecutionTaskResponse(
            id=task.id,
            execution_id=task.execution_id,
            task_id=task.task_id,
            task_name=task.task.name,
            dependencies=task.task.dependencies or [],
            status=task.status,
            retries=task.retries,
            started_at=task.started_at,
            finished_at=task.finished_at,
            error_message=task.error_message,
            worker_id=task.worker_id,
        )
        for task in tasks
    ]


@router.get("/executions/{execution_id}/logs", response_model=list[ExecutionLogResponse])
async def get_execution_logs(
    execution_id: str,
    session: AsyncSession = Depends(get_db_session),
    execution_service=Depends(get_execution_service),
):
    controller = ExecutionController(session, execution_service)
    return await controller.get_logs(execution_id)
