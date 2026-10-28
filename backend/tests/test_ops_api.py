from backend.tests.conftest import ADMIN_KEY, API, OPERATOR_KEY, VIEWER_KEY, auth, create_workflow


async def test_audit_log_records_actions(client):
    await create_workflow(client, name="audited-flow")

    response = await client.get(f"{API}/audit", headers=auth(ADMIN_KEY))
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] >= 1
    assert any(item["action"] == "workflow.created" for item in payload["items"])
    assert all("actor_label" in item for item in payload["items"])

    forbidden = await client.get(f"{API}/audit", headers=auth(OPERATOR_KEY))
    assert forbidden.status_code == 403


async def test_secret_crud_never_returns_plaintext(client):
    created = await client.post(
        f"{API}/secrets",
        headers=auth(ADMIN_KEY),
        json={"name": "deploy-token", "value": "super-sensitive-value"},
    )
    assert created.status_code == 201
    body = created.json()
    assert body["name"] == "deploy-token"
    assert "value" not in body
    assert "ciphertext" not in body

    listed = await client.get(f"{API}/secrets", headers=auth(ADMIN_KEY))
    assert listed.status_code == 200
    assert [item["name"] for item in listed.json()] == ["deploy-token"]
    assert "ciphertext" not in listed.json()[0]

    forbidden = await client.get(f"{API}/secrets", headers=auth(OPERATOR_KEY))
    assert forbidden.status_code == 403

    deleted = await client.delete(f"{API}/secrets/deploy-token", headers=auth(ADMIN_KEY))
    assert deleted.status_code == 204

    missing = await client.delete(f"{API}/secrets/deploy-token", headers=auth(ADMIN_KEY))
    assert missing.status_code == 404


async def test_webhook_crud_and_validation(client):
    invalid = await client.post(
        f"{API}/webhooks",
        headers=auth(ADMIN_KEY),
        json={"url": "ftp://example.com/hook", "secret": "0123456789abcdef"},
    )
    assert invalid.status_code == 422

    unsupported_event = await client.post(
        f"{API}/webhooks",
        headers=auth(ADMIN_KEY),
        json={"url": "https://example.com/hook", "secret": "0123456789abcdef", "events": ["nope"]},
    )
    assert unsupported_event.status_code == 422

    created = await client.post(
        f"{API}/webhooks",
        headers=auth(ADMIN_KEY),
        json={
            "url": "https://example.com/hook",
            "secret": "0123456789abcdef",
            "events": ["execution.failed", "execution.succeeded"],
        },
    )
    assert created.status_code == 201
    endpoint = created.json()
    assert endpoint["events"] == ["execution.failed", "execution.succeeded"]
    assert "secret" not in endpoint

    listed = await client.get(f"{API}/webhooks", headers=auth(ADMIN_KEY))
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    deliveries = await client.get(f"{API}/webhooks/deliveries", headers=auth(ADMIN_KEY))
    assert deliveries.status_code == 200
    assert deliveries.json()["total"] == 0

    deleted = await client.delete(f"{API}/webhooks/{endpoint['id']}", headers=auth(ADMIN_KEY))
    assert deleted.status_code == 204


async def test_diagnostics_exposes_runtime_state(client):
    response = await client.get(f"{API}/diagnostics", headers=auth(ADMIN_KEY))
    assert response.status_code == 200
    payload = response.json()
    assert payload["version"]
    assert isinstance(payload["handlers"], list)
    assert "sleep" in payload["handlers"]
    assert payload["queue"]["queue_backend"] == "database"
    assert payload["dead_letters"] == 0
    assert payload["websockets"] == 0

    forbidden = await client.get(f"{API}/diagnostics", headers=auth(VIEWER_KEY))
    assert forbidden.status_code == 403


async def test_dead_letter_listing_is_empty_by_default(client):
    response = await client.get(f"{API}/queue/dead-letters", headers=auth(ADMIN_KEY))
    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0}


async def test_replaying_unknown_dead_letter_returns_404(client):
    response = await client.post(f"{API}/queue/dead-letters/missing/replay", headers=auth(OPERATOR_KEY))
    assert response.status_code == 404
