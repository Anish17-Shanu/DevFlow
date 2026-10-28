from __future__ import annotations

import asyncio
import logging
from collections import defaultdict

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class RealtimeService:
    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()
        self._bus = None

    def use_bus(self, bus) -> None:
        self._bus = bus

    async def connect(self, execution_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections[execution_id].add(websocket)

    async def disconnect(self, execution_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            if execution_id in self._connections:
                self._connections[execution_id].discard(websocket)
                if not self._connections[execution_id]:
                    self._connections.pop(execution_id, None)

    async def broadcast(self, execution_id: str, payload: dict) -> None:
        await self.broadcast_local(execution_id, payload)
        if self._bus is not None:
            try:
                await self._bus.publish(execution_id, payload)
            except Exception:
                # Local delivery already happened; a bus outage must not break execution.
                logger.warning("Realtime bus publish failed for execution %s.", execution_id, exc_info=True)

    async def broadcast_local(self, execution_id: str, payload: dict) -> None:
        async with self._lock:
            sockets = list(self._connections.get(execution_id, set()))
        stale: list[WebSocket] = []
        for websocket in sockets:
            try:
                await websocket.send_json(payload)
            except Exception:
                stale.append(websocket)
        for websocket in stale:
            await self.disconnect(execution_id, websocket)

    async def connection_count(self) -> int:
        async with self._lock:
            return sum(len(sockets) for sockets in self._connections.values())
