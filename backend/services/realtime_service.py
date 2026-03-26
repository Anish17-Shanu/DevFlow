from __future__ import annotations

import asyncio
from collections import defaultdict

from fastapi import WebSocket


class RealtimeService:
    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

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
