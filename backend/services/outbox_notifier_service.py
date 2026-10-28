from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.core.config import settings
from backend.core.time import utc_now
from backend.models.entities import OutboxEvent, WebhookEndpoint
from backend.services.realtime_service import RealtimeService

logger = logging.getLogger(__name__)


class OutboxNotifierService:
    def __init__(self, session_factory: async_sessionmaker, realtime: RealtimeService) -> None:
        self._session_factory = session_factory
        self._realtime = realtime
        self._task: asyncio.Task | None = None
        self._running = False

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
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
            try:
                await self.poll_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Outbox poll failed; retrying.")
            await asyncio.sleep(interval)

    async def poll_once(self) -> None:
        async with self._session_factory() as session:
            statement = (
                select(OutboxEvent)
                .where(OutboxEvent.processed_at.is_(None))
                .order_by(OutboxEvent.created_at.asc())
                .limit(100)
            )
            if session.bind is not None and session.bind.dialect.name == "postgresql":
                statement = statement.with_for_update(skip_locked=True)
            events = list((await session.execute(statement)).scalars())
            if not events:
                return

            payloads: list[tuple[str | None, dict]] = []
            for event in events:
                payloads.append(
                    (
                        event.execution_id,
                        {
                            "type": event.event_type,
                            "executionId": event.execution_id,
                            "payload": event.payload,
                        },
                    )
                )
                endpoints = list(
                    (
                        await session.execute(
                            select(WebhookEndpoint).where(
                                WebhookEndpoint.tenant_id == event.tenant_id,
                                WebhookEndpoint.is_active.is_(True),
                            )
                        )
                    ).scalars()
                )
                for endpoint in endpoints:
                    if event.event_type in (endpoint.events or []):
                        from backend.models.entities import WebhookDelivery

                        session.add(
                            WebhookDelivery(
                                tenant_id=event.tenant_id,
                                endpoint_id=endpoint.id,
                                event_type=event.event_type,
                                payload={
                                    "event": event.event_type,
                                    "executionId": event.execution_id,
                                    "data": event.payload,
                                    "timestamp": utc_now().isoformat(),
                                },
                            )
                        )
                event.processed_at = utc_now()
            await session.commit()

        for execution_id, payload in payloads:
            if execution_id:
                try:
                    await self._realtime.broadcast(execution_id, payload)
                except Exception:
                    logger.exception("Failed to broadcast outbox event %s.", payload.get("type"))
