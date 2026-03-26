from fastapi import APIRouter, WebSocket, WebSocketDisconnect


router = APIRouter(tags=["realtime"])


@router.websocket("/ws/executions/{execution_id}")
async def execution_updates(websocket: WebSocket, execution_id: str):
    realtime = websocket.app.state.runtime.realtime
    await realtime.connect(execution_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await realtime.disconnect(execution_id, websocket)
