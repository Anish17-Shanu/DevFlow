from backend.core.rate_limit import rate_limiter
from backend.tests.conftest import (
    ADMIN_KEY,
    API,
    OPERATOR_KEY,
    OTHER_ADMIN_KEY,
    VIEWER_KEY,
    auth,
)

WORKFLOW_PAYLOAD = {
    "name": "auth-flow",
    "tasks": [{"name": "only", "config": {"type": "sleep", "duration_ms": 100}}],
}


async def test_requests_without_api_key_are_rejected(client):
    response = await client.get(f"{API}/auth/me")
    assert response.status_code == 401
    assert response.json()["code"] == "unauthorized"


async def test_invalid_api_key_is_rejected(client):
    response = await client.get(f"{API}/auth/me", headers=auth("dvf_not_a_real_key"))
    assert response.status_code == 401


async def test_bearer_token_is_supported(client):
    response = await client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {VIEWER_KEY}"})
    assert response.status_code == 200
    assert response.json()["role"] == "viewer"


async def test_me_returns_principal_context(client):
    response = await client.get(f"{API}/auth/me", headers=auth(OPERATOR_KEY))
    payload = response.json()

    assert response.status_code == 200
    assert payload["tenant_name"] == "Test tenant"
    assert payload["key_name"] == "operator"
    assert payload["role"] == "operator"


async def test_role_hierarchy_enforced(client):
    viewer_create = await client.post(f"{API}/workflows", headers=auth(VIEWER_KEY), json=WORKFLOW_PAYLOAD)
    assert viewer_create.status_code == 403
    assert viewer_create.json()["code"] == "forbidden"

    operator_keys = await client.get(f"{API}/auth/keys", headers=auth(OPERATOR_KEY))
    assert operator_keys.status_code == 403

    operator_create = await client.post(
        f"{API}/workflows", headers=auth(OPERATOR_KEY), json={**WORKFLOW_PAYLOAD, "name": "operator-flow"}
    )
    assert operator_create.status_code == 201

    workflow_id = operator_create.json()["id"]
    operator_delete = await client.delete(f"{API}/workflows/{workflow_id}", headers=auth(OPERATOR_KEY))
    assert operator_delete.status_code == 403

    admin_delete = await client.delete(f"{API}/workflows/{workflow_id}", headers=auth(ADMIN_KEY))
    assert admin_delete.status_code == 204


async def test_workflows_are_tenant_isolated(client):
    created = await client.post(f"{API}/workflows", headers=auth(ADMIN_KEY), json=WORKFLOW_PAYLOAD)
    assert created.status_code == 201
    workflow_id = created.json()["id"]

    other_get = await client.get(f"{API}/workflows/{workflow_id}", headers=auth(OTHER_ADMIN_KEY))
    assert other_get.status_code == 404

    other_list = await client.get(f"{API}/workflows", headers=auth(OTHER_ADMIN_KEY))
    assert other_list.status_code == 200
    assert other_list.json()["total"] == 0

    other_run = await client.post(f"{API}/workflows/{workflow_id}/run", headers=auth(OTHER_ADMIN_KEY))
    assert other_run.status_code == 404


async def test_api_key_lifecycle_and_immediate_revocation(client):
    created = await client.post(
        f"{API}/auth/keys",
        headers=auth(ADMIN_KEY),
        json={"name": "ci-key", "role": "operator"},
    )
    assert created.status_code == 201
    raw_key = created.json()["key"]
    key_id = created.json()["id"]
    assert raw_key.startswith("dvf_")

    me = await client.get(f"{API}/auth/me", headers=auth(raw_key))
    assert me.status_code == 200
    assert me.json()["role"] == "operator"

    listed = await client.get(f"{API}/auth/keys", headers=auth(ADMIN_KEY))
    assert listed.status_code == 200
    assert any(item["id"] == key_id for item in listed.json())
    assert all("key" not in item for item in listed.json())

    revoked = await client.delete(f"{API}/auth/keys/{key_id}", headers=auth(ADMIN_KEY))
    assert revoked.status_code == 204

    after_revoke = await client.get(f"{API}/auth/me", headers=auth(raw_key))
    assert after_revoke.status_code == 401


async def test_cannot_revoke_key_in_use(client):
    me = await client.get(f"{API}/auth/me", headers=auth(ADMIN_KEY))
    key_id = me.json()["key_id"]

    response = await client.delete(f"{API}/auth/keys/{key_id}", headers=auth(ADMIN_KEY))
    assert response.status_code == 400


async def test_revoking_unknown_key_returns_404(client):
    response = await client.delete(f"{API}/auth/keys/does-not-exist", headers=auth(ADMIN_KEY))
    assert response.status_code == 404


async def test_create_key_validates_role(client):
    response = await client.post(
        f"{API}/auth/keys",
        headers=auth(ADMIN_KEY),
        json={"name": "bad-role", "role": "superuser"},
    )
    assert response.status_code == 422


async def test_rate_limiter_returns_retry_after(client, monkeypatch):
    monkeypatch.setattr(rate_limiter, "burst", 1.0)
    rate_limiter._buckets.clear()

    first = await client.get(f"{API}/auth/me", headers=auth(VIEWER_KEY))
    second = await client.get(f"{API}/auth/me", headers=auth(VIEWER_KEY))

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json()["code"] == "rate_limited"
    assert "Retry-After" in second.headers


async def test_v1_prefix_is_required(client):
    response = await client.get("/api/workflows", headers=auth(ADMIN_KEY))
    assert response.status_code == 404
