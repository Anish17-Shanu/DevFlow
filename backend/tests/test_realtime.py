from __future__ import annotations

from types import SimpleNamespace

import pytest
from starlette.websockets import WebSocketDisconnect

from backend.api.dependencies import authenticate_websocket
from backend.api.routes import websocket_routes
from backend.models.entities import Execution, ExecutionStatus
from backend.services.realtime_service import RealtimeService
from backend.tests.conftest import OTHER_TENANT_ID, TENANT_ID, seed_tenants_and_keys


class FakeWebSocket:
    def __init__(self, api_key: str | None = None, *, app=None) -> None:
        self.query_params = {"api_key": api_key} if api_key else {}
        self.headers: dict[str, str] = {}
        self.app = app or SimpleNamespace(state=SimpleNamespace(runtime=SimpleNamespace(realtime=RealtimeService())))
        self.accepted = False
        self.close_calls: list[tuple[int, str]] = []
        self.receive_calls = 0

    async def accept(self) -> None:
        self.accepted = True

    async def close(self, code: int = 1000, reason: str = "") -> None:
        self.close_calls.append((code, reason))

    async def receive_text(self) -> str:
        self.receive_calls += 1
        raise WebSocketDisconnect(code=1006)


@pytest.fixture
async def seeded(session_factory):
    await seed_tenants_and_keys(session_factory)
    return session_factory


async def _add_execution(session_factory, tenant_id: str) -> str:
    async with session_factory() as session:
        execution = Execution(
            tenant_id=tenant_id,
            workflow_id="workflow-1",
            workflow_name="realtime-test",
            snapshot={},
            status=ExecutionStatus.running,
        )
        session.add(execution)
        await session.commit()
        await session.refresh(execution)
        return execution.id


async def test_websocket_requires_an_api_key():
    websocket = FakeWebSocket()
    assert await authenticate_websocket(websocket) is None
    assert websocket.close_calls == [(1008, "Missing API key.")]


async def test_websocket_rejects_invalid_keys(seeded, monkeypatch):
    monkeypatch.setattr("backend.core.database.SessionLocal", seeded)
    websocket = FakeWebSocket(api_key="not-a-real-key")
    assert await authenticate_websocket(websocket) is None
    assert websocket.close_calls == [(1008, "Invalid API key.")]


async def test_websocket_principal_is_tenant_scoped(seeded, monkeypatch):
    from backend.tests.conftest import ADMIN_KEY

    monkeypatch.setattr("backend.core.database.SessionLocal", seeded)
    websocket = FakeWebSocket(api_key=ADMIN_KEY)
    principal = await authenticate_websocket(websocket)
    assert principal is not None
    assert principal.tenant_id == TENANT_ID
    assert websocket.close_calls == []


async def test_websocket_rejects_cross_tenant_execution(seeded, monkeypatch):
    monkeypatch.setattr(websocket_routes, "SessionLocal", seeded)
    execution_id = await _add_execution(seeded, OTHER_TENANT_ID)
    websocket = FakeWebSocket(api_key="dvf_test_admin_key_0000000000000000")

    await websocket_routes.execution_updates(websocket, execution_id)

    assert websocket.close_calls == [(1008, "Execution not found.")]
    assert websocket.accepted is False


async def test_websocket_subscribes_and_cleans_up_on_disconnect(seeded, monkeypatch):
    monkeypatch.setattr(websocket_routes, "SessionLocal", seeded)
    execution_id = await _add_execution(seeded, TENANT_ID)
    runtime = SimpleNamespace(state=SimpleNamespace(runtime=SimpleNamespace(realtime=RealtimeService())))
    websocket = FakeWebSocket(api_key="dvf_test_admin_key_0000000000000000", app=runtime)

    await websocket_routes.execution_updates(websocket, execution_id)

    assert websocket.accepted is True
    assert websocket.close_calls == []
    assert websocket.receive_calls == 1
    assert await runtime.state.runtime.realtime.connection_count() == 0


class RecordingWebSocket:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    async def accept(self) -> None:
        return None

    async def send_json(self, payload: dict) -> None:
        self.messages.append(payload)


class RecordingBus:
    def __init__(self) -> None:
        self.published: list[tuple[str, dict]] = []

    async def publish(self, execution_id: str, payload: dict) -> None:
        self.published.append((execution_id, payload))


async def test_broadcast_delivers_locally_and_publishes_to_bus_once():
    service = RealtimeService()
    socket = RecordingWebSocket()
    bus = RecordingBus()
    service.use_bus(bus)
    await service.connect("exec-1", socket)

    await service.broadcast("exec-1", {"status": "success"})

    assert socket.messages == [{"status": "success"}]
    assert bus.published == [("exec-1", {"status": "success"})]


async def test_broadcast_local_skips_the_bus():
    service = RealtimeService()
    socket = RecordingWebSocket()
    bus = RecordingBus()
    service.use_bus(bus)
    await service.connect("exec-1", socket)

    await service.broadcast_local("exec-1", {"status": "success"})

    assert socket.messages == [{"status": "success"}]
    assert bus.published == []


async def test_broadcast_survives_bus_failures():
    class FailingBus:
        async def publish(self, execution_id: str, payload: dict) -> None:
            raise RuntimeError("bus down")

    service = RealtimeService()
    socket = RecordingWebSocket()
    service.use_bus(FailingBus())
    await service.connect("exec-1", socket)

    await service.broadcast("exec-1", {"status": "success"})

    assert socket.messages == [{"status": "success"}]
