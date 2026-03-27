from __future__ import annotations

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.core.config import settings
from backend.core.time import utc_now
from backend.models.entities import Execution
from backend.services.realtime_service import RealtimeService


class ExecutionNotifierService:
    def __init__(self, session_factory: async_sessionmaker, realtime: RealtimeService) -> None:
        self._session_factory = session_factory
        self._realtime = realtime
        self._task: asyncio.Task | None = None
        self._running = False
        self._cursor = utc_now()

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._cursor = utc_now()
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._running = False
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    async def _run(self) -> None:
        interval = settings.realtime_poll_interval_ms / 1000
        while self._running:
            async with self._session_factory() as session:
                result = await session.execute(
                    select(Execution.id, Execution.updated_at)
                    .where(Execution.updated_at > self._cursor)
                    .order_by(Execution.updated_at.asc(), Execution.id.asc())
                )
                rows = result.all()

            next_cursor = self._cursor
            for row in rows:
                await self._realtime.broadcast(row.id, {"type": "execution.updated", "executionId": row.id})
                if row.updated_at and row.updated_at >= next_cursor:
                    next_cursor = row.updated_at

            self._cursor = next_cursor
            await asyncio.sleep(interval)
