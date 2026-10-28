from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from backend.api.dependencies import authenticate_websocket
from backend.core.database import SessionLocal
from backend.models.entities import Execution

router = APIRouter(tags=["realtime"])


@router.websocket("/ws/executions/{execution_id}")
async def execution_updates(websocket: WebSocket, execution_id: str):
    principal = await authenticate_websocket(websocket)
    if principal is None:
        return

    async with SessionLocal() as session:
        owner = await session.scalar(select(Execution.tenant_id).where(Execution.id == execution_id))
    if owner is None or owner != principal.tenant_id:
        await websocket.close(code=1008, reason="Execution not found.")
        return

    realtime = websocket.app.state.runtime.realtime
    await realtime.connect(execution_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await realtime.disconnect(execution_id, websocket)
