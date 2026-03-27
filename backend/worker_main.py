import asyncio
import logging

from backend.core.config import settings
from backend.core.database import Base, SessionLocal, engine
from backend.queue.job_queue import DatabaseJobQueue
from backend.services.execution_service import ExecutionService
from backend.services.migration_service import MigrationService
from backend.services.realtime_service import RealtimeService
from backend.workers.runtime import WorkerManager


async def run_workers() -> None:
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        await connection.run_sync(MigrationService.apply)

    queue = DatabaseJobQueue(SessionLocal)
    execution_service = ExecutionService(queue, RealtimeService())
    worker_manager = WorkerManager(queue, execution_service, SessionLocal)

    await worker_manager.start()
    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        await worker_manager.stop()


if __name__ == "__main__":
    asyncio.run(run_workers())
