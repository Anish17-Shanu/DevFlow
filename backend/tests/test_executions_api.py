from backend.tests.conftest import ADMIN_KEY, API, OPERATOR_KEY, OTHER_ADMIN_KEY, VIEWER_KEY, auth, create_workflow


async def _run(client, workflow_id: str, headers: dict | None = None, idempotency_key: str | None = None):
    extra = {"Idempotency-Key": idempotency_key} if idempotency_key else {}
    return await client.post(f"{API}/workflows/{workflow_id}/run", headers={**auth(OPERATOR_KEY), **extra})


async def test_run_execution_and_read_views(client):
    workflow = await create_workflow(client, name="run-flow")
    response = await _run(client, workflow["id"])

    assert response.status_code == 200
    execution = response.json()
    assert execution["status"] == "running"
    assert execution["workflow_id"] == workflow["id"]
    assert execution["triggered_by"].startswith("operator")

    detail = await client.get(f"{API}/executions/{execution['id']}", headers=auth(VIEWER_KEY))
    assert detail.status_code == 200
    assert detail.json()["id"] == execution["id"]

    tasks = await client.get(f"{API}/executions/{execution['id']}/tasks", headers=auth(VIEWER_KEY))
    assert tasks.status_code == 200
    assert [task["task_name"] for task in tasks.json()] == ["extract", "load"]
    assert [task["status"] for task in tasks.json()] == ["queued", "pending"]

    logs = await client.get(f"{API}/executions/{execution['id']}/logs", headers=auth(VIEWER_KEY))
    assert logs.status_code == 200
    body = logs.json()
    assert body["items"]
    assert any("Execution created" in item["message"] for item in body["items"])
    assert "next_cursor" in body

    listed = await client.get(f"{API}/executions", headers=auth(VIEWER_KEY))
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    filtered = await client.get(f"{API}/executions?status=failed", headers=auth(VIEWER_KEY))
    assert filtered.json()["total"] == 0

    by_workflow = await client.get(f"{API}/executions?workflow_id={workflow['id']}", headers=auth(VIEWER_KEY))
    assert by_workflow.json()["total"] == 1


async def test_idempotency_key_returns_existing_execution(client):
    workflow = await create_workflow(client, name="idem-flow")

    first = await _run(client, workflow["id"], idempotency_key="idem-1")
    second = await _run(client, workflow["id"], idempotency_key="idem-1")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]

    listed = await client.get(f"{API}/executions", headers=auth(VIEWER_KEY))
    assert listed.json()["total"] == 1


async def test_executions_are_tenant_isolated(client):
    workflow = await create_workflow(client, name="isolated-flow")
    execution = (await _run(client, workflow["id"])).json()

    for path in ("", "/tasks", "/logs"):
        response = await client.get(f"{API}/executions/{execution['id']}{path}", headers=auth(OTHER_ADMIN_KEY))
        assert response.status_code == 404, path

    cancel = await client.post(f"{API}/executions/{execution['id']}/cancel", headers=auth(OTHER_ADMIN_KEY))
    assert cancel.status_code == 404


async def test_cancel_queued_execution(client):
    workflow = await create_workflow(client, name="cancel-flow")
    execution = (await _run(client, workflow["id"])).json()

    cancelled = await client.post(f"{API}/executions/{execution['id']}/cancel", headers=auth(OPERATOR_KEY))
    assert cancelled.status_code == 200
    body = cancelled.json()
    assert body["status"] == "cancelled"
    assert body["cancellation_requested"] is True
    assert body["finished_at"] is not None

    tasks = await client.get(f"{API}/executions/{execution['id']}/tasks", headers=auth(VIEWER_KEY))
    assert {task["status"] for task in tasks.json()} == {"cancelled"}

    queue_status = await client.get(f"{API}/queue/status", headers=auth(OPERATOR_KEY))
    assert queue_status.status_code == 200
    assert queue_status.json()["queued_jobs"] == 0
    assert queue_status.json()["in_flight_jobs"] == 0

    again = await client.post(f"{API}/executions/{execution['id']}/cancel", headers=auth(OPERATOR_KEY))
    assert again.status_code == 200
    assert again.json()["status"] == "cancelled"


async def test_retry_execution_creates_new_run(client):
    workflow = await create_workflow(client, name="retry-flow")
    execution = (await _run(client, workflow["id"])).json()
    await client.post(f"{API}/executions/{execution['id']}/cancel", headers=auth(OPERATOR_KEY))

    retried = await client.post(f"{API}/executions/{execution['id']}/retry", headers=auth(OPERATOR_KEY))
    assert retried.status_code == 200
    body = retried.json()
    assert body["id"] != execution["id"]
    assert body["status"] == "running"

    logs = await client.get(f"{API}/executions/{body['id']}/logs", headers=auth(VIEWER_KEY))
    assert any("retried from" in item["message"] for item in logs.json()["items"])


async def test_task_retry_and_skip_actions(client):
    workflow = await create_workflow(
        client,
        name="task-actions-flow",
        tasks=[
            {"name": "first", "config": {"duration_ms": 100}},
            {"name": "second", "dependencies": ["first"], "config": {}},
        ],
    )
    execution = (await _run(client, workflow["id"])).json()
    await client.post(f"{API}/executions/{execution['id']}/cancel", headers=auth(OPERATOR_KEY))

    retried = await client.post(f"{API}/executions/{execution['id']}/tasks/first/retry", headers=auth(OPERATOR_KEY))
    assert retried.status_code == 200
    assert retried.json()["status"] == "running"

    tasks = await client.get(f"{API}/executions/{execution['id']}/tasks", headers=auth(VIEWER_KEY))
    states = {task["task_name"]: task["status"] for task in tasks.json()}
    assert states["first"] == "queued"
    assert states["second"] == "pending"

    skipped = await client.post(f"{API}/executions/{execution['id']}/tasks/first/skip", headers=auth(OPERATOR_KEY))
    assert skipped.status_code == 200

    tasks = await client.get(f"{API}/executions/{execution['id']}/tasks", headers=auth(VIEWER_KEY))
    states = {task["task_name"]: task["status"] for task in tasks.json()}
    assert states["first"] == "skipped"
    assert states["second"] == "queued"

    unknown = await client.post(f"{API}/executions/{execution['id']}/tasks/ghost/retry", headers=auth(OPERATOR_KEY))
    assert unknown.status_code == 404


async def test_unknown_execution_returns_404(client):
    response = await client.get(f"{API}/executions/missing", headers=auth(VIEWER_KEY))
    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


async def test_operator_can_read_queue_status_but_only_admin_sees_workers(client):
    allowed = await client.get(f"{API}/queue/status", headers=auth(OPERATOR_KEY))
    assert allowed.status_code == 200
    assert allowed.json()["queue_backend"] == "database"

    forbidden = await client.get(f"{API}/workers/status", headers=auth(OPERATOR_KEY))
    assert forbidden.status_code == 403

    admin = await client.get(f"{API}/workers/status", headers=auth(ADMIN_KEY))
    assert admin.status_code == 200
    assert admin.json() == []

    snapshot = await client.get(f"{API}/system/snapshot", headers=auth(ADMIN_KEY))
    assert snapshot.status_code == 200
    assert snapshot.json()["queue"]["queue_backend"] == "database"
