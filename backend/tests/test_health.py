from httpx import ASGITransport, AsyncClient

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
