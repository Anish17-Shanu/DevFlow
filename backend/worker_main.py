import asyncio
import logging
import signal

from backend.core.config import settings
from backend.core.database import SessionLocal, engine
from backend.core.logging import setup_logging
from backend.queue.job_queue import DatabaseJobQueue
from backend.services.auth_service import AuthService
from backend.services.execution_service import ExecutionService
from backend.services.migration_service import MigrationService
from backend.services.realtime_service import RealtimeService
from backend.services.retention_service import RetentionService
from backend.services.scheduler_service import SchedulerService
from backend.services.watchdog_service import WatchdogService
from backend.services.webhook_service import WebhookDispatcherService
from backend.workers.heartbeat import write_heartbeat_loop
from backend.workers.runtime import WorkerManager


async def run_workers() -> None:
    setup_logging()
    if settings.auto_migrate:
        await MigrationService.upgrade()

    async with SessionLocal() as session:
        await AuthService(session).ensure_bootstrap()

    queue = DatabaseJobQueue(SessionLocal)
    execution_service = ExecutionService(queue, RealtimeService())
    worker_manager = WorkerManager(queue, execution_service, SessionLocal)
    watchdog = WatchdogService(SessionLocal, queue, execution_service)
    scheduler = SchedulerService(SessionLocal, execution_service)
    retention = RetentionService(SessionLocal)
    webhooks = WebhookDispatcherService(SessionLocal)

    stop_event = asyncio.Event()

    def request_shutdown(*_args) -> None:
        logging.getLogger(__name__).info("Shutdown signal received; draining workers.")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for signal_name in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(signal_name, request_shutdown)
        except NotImplementedError:
            signal.signal(signal_name, request_shutdown)

    heartbeat_task = asyncio.create_task(write_heartbeat_loop(stop_event, settings.worker_heartbeat_interval_seconds))

    await worker_manager.start()
    await watchdog.start()
    await scheduler.start()
    await retention.start()
    await webhooks.start()
    try:
        await stop_event.wait()
    finally:
        await webhooks.stop()
        await retention.stop()
        await scheduler.stop()
        await watchdog.stop()
        await worker_manager.stop()
        await stop_event.set()
        await heartbeat_task
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run_workers())
