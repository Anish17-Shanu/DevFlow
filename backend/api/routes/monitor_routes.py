from fastapi import APIRouter, Depends

from backend.api.dependencies import get_queue, get_worker_manager
from backend.controllers.monitor_controller import MonitorController
from backend.schemas.workflow import QueueStatusResponse, SystemSnapshotResponse, WorkerStatusResponse


router = APIRouter(tags=["monitoring"])


@router.get("/queue/status", response_model=QueueStatusResponse)
async def get_queue_status(queue=Depends(get_queue), worker_manager=Depends(get_worker_manager)):
    controller = MonitorController(queue, worker_manager)
    return await controller.queue_status()


@router.get("/workers/status", response_model=list[WorkerStatusResponse])
async def get_workers_status(queue=Depends(get_queue), worker_manager=Depends(get_worker_manager)):
    controller = MonitorController(queue, worker_manager)
    return await controller.worker_status()


@router.get("/system/snapshot", response_model=SystemSnapshotResponse)
async def get_system_snapshot(queue=Depends(get_queue), worker_manager=Depends(get_worker_manager)):
    controller = MonitorController(queue, worker_manager)
    return await controller.snapshot()
