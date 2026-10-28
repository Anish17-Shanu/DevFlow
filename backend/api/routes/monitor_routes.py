from fastapi import APIRouter, Depends

from backend.api.dependencies import get_queue, get_worker_manager, require_role
from backend.controllers.monitor_controller import MonitorController
from backend.core.security import Principal
from backend.schemas.workflow import QueueStatusResponse, SystemSnapshotResponse, WorkerStatusResponse

router = APIRouter(tags=["monitoring"])


@router.get("/queue/status", response_model=QueueStatusResponse)
async def get_queue_status(
    principal: Principal = Depends(require_role("operator")),
    queue=Depends(get_queue),
    worker_manager=Depends(get_worker_manager),
):
    return await MonitorController(queue, worker_manager).queue_status(principal.tenant_id)


@router.get("/workers/status", response_model=list[WorkerStatusResponse])
async def get_workers_status(
    principal: Principal = Depends(require_role("admin")),
    queue=Depends(get_queue),
    worker_manager=Depends(get_worker_manager),
):
    return await MonitorController(queue, worker_manager).worker_status()


@router.get("/system/snapshot", response_model=SystemSnapshotResponse)
async def get_system_snapshot(
    principal: Principal = Depends(require_role("admin")),
    queue=Depends(get_queue),
    worker_manager=Depends(get_worker_manager),
):
    return await MonitorController(queue, worker_manager).snapshot(None)
