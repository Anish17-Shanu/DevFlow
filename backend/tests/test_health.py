from httpx import ASGITransport, AsyncClient

from backend.core.config import settings
from backend.main import app


async def test_health_endpoint_reports_service_metadata():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"] == "DevFlow"
    assert "timestamp" in payload


async def test_readiness_endpoint_reports_queue_shape():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.get("/health/ready")

    assert response.status_code == 200
    payload = response.json()
    assert payload["queue"]["queue_backend"] == "database"
    assert payload["queue"]["is_durable"] is True


async def test_responses_carry_security_headers():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.get("/health")

    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-request-id"]


async def test_oversized_request_body_is_rejected(monkeypatch):
    monkeypatch.setattr(settings, "max_request_body_bytes", 10)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.post("/api/workflows", json={"name": "too-large", "tasks": [{"name": "task"}]})

    assert response.status_code == 413


async def test_log_pagination_parameters_are_validated():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.get("/api/executions/unknown/logs?limit=0")

    assert response.status_code == 422
