from httpx import ASGITransport, AsyncClient

from backend.core.config import settings
from backend.main import app
from backend.tests.conftest import API, VIEWER_KEY, auth


async def test_health_endpoint_reports_service_metadata():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.get("/health")
        live = await client.get("/health/live")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"] == "DevFlow"
    assert "timestamp" in payload
    assert live.json()["status"] == "ok"


async def test_readiness_endpoint_reports_queue_shape(client, session_factory, runtime, monkeypatch):
    import backend.main as main_module

    monkeypatch.setattr(main_module, "engine", session_factory.kw["bind"])
    monkeypatch.setattr(main_module, "runtime", runtime)

    response = await client.get("/health/ready")

    assert response.status_code == 200
    payload = response.json()
    assert payload["database"] == "ok"
    assert payload["queue"]["queue_backend"] == "database"
    assert payload["queue"]["is_durable"] is True


async def test_responses_carry_security_headers_and_request_id():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.get("/health", headers={"X-Request-ID": "test-request-1234"})

    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-request-id"] == "test-request-1234"


async def test_oversized_request_body_is_rejected(client, monkeypatch):
    monkeypatch.setattr(settings, "max_request_body_bytes", 10)
    response = await client.post(
        f"{API}/workflows",
        headers=auth(VIEWER_KEY),
        json={"name": "too-large", "tasks": [{"name": "task"}]},
    )
    assert response.status_code == 413
    assert response.json()["code"] == "payload_too_large"


async def test_validation_errors_use_structured_shape(client):
    response = await client.get(f"{API}/executions/unknown/logs?limit=0", headers=auth(VIEWER_KEY))
    payload = response.json()

    assert response.status_code == 422
    assert payload["code"] == "validation_error"
    assert payload["request_id"] == response.headers["x-request-id"]
    assert payload["details"]


async def test_metrics_endpoint_exposes_prometheus_series(client):
    response = await client.get("/metrics")
    assert response.status_code == 200
    assert "devflow_http_requests_total" in response.text


async def test_metrics_can_be_disabled(client, monkeypatch):
    monkeypatch.setattr(settings, "metrics_enabled", False)
    response = await client.get("/metrics")
    assert response.status_code == 404
