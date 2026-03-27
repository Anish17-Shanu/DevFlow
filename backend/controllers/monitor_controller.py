from backend.schemas.workflow import QueueStatusResponse, SystemSnapshotResponse, WorkerStatusResponse


class MonitorController:
    def __init__(self, queue, worker_manager):
        self.queue = queue
        self.worker_manager = worker_manager

    async def queue_status(self) -> QueueStatusResponse:
        return QueueStatusResponse(**(await self.queue.stats()))

    async def worker_status(self) -> list[WorkerStatusResponse]:
        return [WorkerStatusResponse(**snapshot.__dict__) for snapshot in await self.worker_manager.snapshots()]

    async def snapshot(self) -> SystemSnapshotResponse:
        return SystemSnapshotResponse(
            queue=QueueStatusResponse(**(await self.queue.stats())),
            workers=[WorkerStatusResponse(**snapshot.__dict__) for snapshot in await self.worker_manager.snapshots()],
        )
