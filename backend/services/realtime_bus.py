from __future__ import annotations

import asyncio
import json
import logging
import uuid

import asyncpg

from backend.core.config import settings

logger = logging.getLogger(__name__)


class PostgresRealtimeBus:
    """Cross-replica websocket fan-out using Postgres LISTEN/NOTIFY.

    Each API process publishes execution events to a shared channel and listens for
    events from other processes. Events published by the same process are skipped
    because the local broadcast already delivered them.
    """

    def __init__(self, dsn: str, channel: str = "devflow_events") -> None:
        self._dsn = dsn
        self._channel = channel
        self._origin = uuid.uuid4().hex
        self._connection: asyncpg.Connection | None = None
        self._listener = None
        self._tasks: set[asyncio.Task] = set()
        self._publish_lock = asyncio.Lock()

    @property
    def channel(self) -> str:
        return self._channel

    async def start(self, on_event) -> None:
        self._listener = on_event
        self._connection = await asyncpg.connect(self._dsn)
        await self._connection.add_listener(self._channel, self._on_notification)
        logger.info("Realtime bus listening on channel %s", self._channel)

    def _on_notification(self, _connection, _pid, _channel, payload: str) -> None:
        try:
            message = json.loads(payload)
            execution_id = message["execution_id"]
            event = message["payload"]
        except (ValueError, KeyError, TypeError):
            logger.warning("Ignoring malformed realtime bus message.")
            return
        if message.get("origin") == self._origin or self._listener is None:
            return
        task = asyncio.create_task(self._listener(execution_id, event))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def publish(self, execution_id: str, payload: dict) -> None:
        if self._connection is None:
            return
        message = json.dumps(
            {"origin": self._origin, "execution_id": execution_id, "payload": payload},
            separators=(",", ":"),
        )
        if len(message.encode("utf-8")) > 7900:
            logger.warning("Realtime bus payload for %s exceeds the NOTIFY limit; skipping fan-out.", execution_id)
            return
        async with self._publish_lock:
            if self._connection is None:
                return
            await self._connection.execute("SELECT pg_notify($1, $2)", self._channel, message)

    async def stop(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        if self._connection is None:
            return
        try:
            await self._connection.remove_listener(self._channel, self._on_notification)
        except Exception:
            logger.exception("Failed to remove realtime bus listener.")
        await self._connection.close()
        self._connection = None


def build_realtime_bus() -> PostgresRealtimeBus | None:
    if settings.realtime_bus not in {"auto", "postgres"}:
        return None
    if not settings.database_url.startswith("postgresql"):
        return None
    dsn = settings.database_url.replace("postgresql+asyncpg://", "postgresql://").replace(
        "postgresql+psycopg://", "postgresql://"
    )
    return PostgresRealtimeBus(dsn, settings.realtime_channel)
