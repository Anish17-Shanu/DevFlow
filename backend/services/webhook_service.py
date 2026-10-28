from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
from datetime import timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.core.config import settings
from backend.core.time import utc_now
from backend.models.entities import WebhookDelivery, WebhookEndpoint

logger = logging.getLogger(__name__)


class WebhookDispatcherService:
    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._session_factory = session_factory
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
        while self._running:
            try:
                await self.dispatch_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Webhook dispatcher failed; retrying.")
            await asyncio.sleep(2)

    async def dispatch_once(self) -> None:
        now = utc_now()
        async with self._session_factory() as session:
            statement = (
                select(WebhookDelivery, WebhookEndpoint)
                .join(WebhookEndpoint, WebhookEndpoint.id == WebhookDelivery.endpoint_id)
                .where(
                    WebhookDelivery.status == "pending",
                    WebhookDelivery.next_attempt_at <= now,
                )
                .order_by(WebhookDelivery.next_attempt_at.asc())
                .limit(20)
            )
            if session.bind is not None and session.bind.dialect.name == "postgresql":
                statement = statement.with_for_update(skip_locked=True)
            rows = list((await session.execute(statement)).all())
            if not rows:
                return

            for delivery, endpoint in rows:
                delivery.attempts += 1
                body = json.dumps(delivery.payload, separators=(",", ":"), sort_keys=True)
                signature = hmac.new(endpoint.secret.encode("utf-8"), body.encode("utf-8"), hashlib.sha256).hexdigest()
                try:
                    async with httpx.AsyncClient(timeout=settings.webhook_timeout_seconds) as client:
                        response = await client.post(
                            endpoint.url,
                            content=body,
                            headers={
                                "Content-Type": "application/json",
                                "X-DevFlow-Signature": f"sha256={signature}",
                                "X-DevFlow-Event": delivery.event_type,
                            },
                        )
                    if 200 <= response.status_code < 300:
                        delivery.status = "delivered"
                        delivery.delivered_at = utc_now()
                        delivery.last_error = None
                    else:
                        delivery.last_error = f"Endpoint returned {response.status_code}."
                except httpx.HTTPError as exc:
                    delivery.last_error = f"{exc.__class__.__name__}: {exc}"[:2000]

                if delivery.status != "delivered":
                    if delivery.attempts >= settings.webhook_max_attempts:
                        delivery.status = "failed"
                    else:
                        delivery.next_attempt_at = utc_now() + timedelta(seconds=min(2**delivery.attempts, 300))
            await session.commit()
