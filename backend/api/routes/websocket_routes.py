from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from backend.core.database import SessionLocal
from backend.models.entities import Execution

router = APIRouter(tags=["realtime"])


@router.websocket("/ws/executions/{execution_id}")
async def execution_updates(websocket: WebSocket, execution_id: str):
    async with SessionLocal() as session:
        execution_exists = await session.scalar(select(Execution.id).where(Execution.id == execution_id))
    if not execution_exists:
        await websocket.close(code=1008, reason="Execution not found.")
        return

    realtime = websocket.app.state.runtime.realtime
    await realtime.connect(execution_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await realtime.disconnect(execution_id, websocket)
