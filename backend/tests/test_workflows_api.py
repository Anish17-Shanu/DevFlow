from backend.tests.conftest import ADMIN_KEY, API, OPERATOR_KEY, VIEWER_KEY, auth, create_workflow


async def test_template_gallery_is_available_to_viewers(client):
    response = await client.get(f"{API}/workflows/templates", headers=auth(VIEWER_KEY))

    assert response.status_code == 200
    templates = response.json()
    assert templates
    assert all("name" in template and "tasks" in template for template in templates)

    created = await client.post(
        f"{API}/workflows", headers=auth(OPERATOR_KEY), json={**templates[0], "name": "from-template"}
    )
    assert created.status_code == 201
    assert created.json()["tasks"]


async def test_workflow_crud_and_revisions(client):
    workflow = await create_workflow(client, name="crud-flow")
    workflow_id = workflow["id"]
    assert workflow["current_revision"] == 1
    assert [task["name"] for task in workflow["tasks"]] == ["extract", "load"]

    listed = await client.get(f"{API}/workflows", headers=auth(VIEWER_KEY))
    assert listed.status_code == 200
    payload = listed.json()
    assert payload["total"] == 1
    assert payload["items"][0]["id"] == workflow_id

    fetched = await client.get(f"{API}/workflows/{workflow_id}", headers=auth(VIEWER_KEY))
    assert fetched.status_code == 200
    assert fetched.json()["name"] == "crud-flow"

    updated = await client.patch(
        f"{API}/workflows/{workflow_id}",
        headers=auth(OPERATOR_KEY),
        json={
            "description": "updated",
            "tasks": [
                {"name": "extract", "config": {"duration_ms": 150}},
                {"name": "transform", "dependencies": ["extract"], "config": {}},
                {"name": "load", "dependencies": ["transform"], "config": {}},
            ],
        },
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["description"] == "updated"
    assert body["current_revision"] == 2
    assert len(body["tasks"]) == 3

    revisions = await client.get(f"{API}/workflows/{workflow_id}/revisions", headers=auth(VIEWER_KEY))
    assert revisions.status_code == 200
    documents = revisions.json()
    assert [item["revision"] for item in documents] == [2, 1]
    assert len(documents[0]["document"]["tasks"]) == 3
    assert documents[0]["created_by"].startswith("operator")

    exported = await client.get(f"{API}/workflows/{workflow_id}/export", headers=auth(VIEWER_KEY))
    assert exported.status_code == 200
    assert exported.json()["revision"] == 2

    imported = await client.post(
        f"{API}/workflows/import",
        headers=auth(OPERATOR_KEY),
        json={**exported.json(), "name": "imported-flow"},
    )
    assert imported.status_code == 201
    assert imported.json()["name"] == "imported-flow"


async def test_workflow_archive_hides_from_default_listing(client):
    workflow = await create_workflow(client, name="archive-flow")
    workflow_id = workflow["id"]

    archived = await client.delete(f"{API}/workflows/{workflow_id}", headers=auth(ADMIN_KEY))
    assert archived.status_code == 204

    visible = await client.get(f"{API}/workflows", headers=auth(VIEWER_KEY))
    assert all(item["id"] != workflow_id for item in visible.json()["items"])

    everything = await client.get(f"{API}/workflows?include_archived=true", headers=auth(VIEWER_KEY))
    assert any(item["id"] == workflow_id for item in everything.json()["items"])

    run_archived = await client.post(f"{API}/workflows/{workflow_id}/run", headers=auth(OPERATOR_KEY))
    assert run_archived.status_code == 404


async def test_duplicate_workflow_names_conflict(client):
    await create_workflow(client, name="duplicate-flow")
    duplicate = await client.post(
        f"{API}/workflows",
        headers=auth(OPERATOR_KEY),
        json={"name": "duplicate-flow", "tasks": [{"name": "only"}]},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "conflict"


async def test_invalid_dag_is_rejected(client):
    cyclic = await client.post(
        f"{API}/workflows",
        headers=auth(OPERATOR_KEY),
        json={
            "name": "cyclic",
            "tasks": [
                {"name": "a", "dependencies": ["b"]},
                {"name": "b", "dependencies": ["a"]},
            ],
        },
    )
    assert cyclic.status_code == 400

    missing_dependency = await client.post(
        f"{API}/workflows",
        headers=auth(OPERATOR_KEY),
        json={"name": "missing-dep", "tasks": [{"name": "a", "dependencies": ["ghost"]}]},
    )
    assert missing_dependency.status_code == 400


async def test_clone_workflow(client):
    source = await create_workflow(client, name="source-flow")
    cloned = await client.post(
        f"{API}/workflows/{source['id']}/clone",
        headers=auth(OPERATOR_KEY),
        json={"name": "cloned-flow"},
    )

    assert cloned.status_code == 201
    body = cloned.json()
    assert body["name"] == "cloned-flow"
    assert body["id"] != source["id"]
    assert len(body["tasks"]) == len(source["tasks"])

    default_name = await client.post(f"{API}/workflows/{source['id']}/clone", headers=auth(OPERATOR_KEY), json={})
    assert default_name.status_code == 201
    assert default_name.json()["name"] == "source-flow copy"


async def test_schedules_are_validated_and_listed(client):
    workflow = await create_workflow(client, name="scheduled-flow")
    workflow_id = workflow["id"]

    created = await client.post(
        f"{API}/workflows/{workflow_id}/schedules",
        headers=auth(OPERATOR_KEY),
        json={"cron": "*/5 * * * *"},
    )
    assert created.status_code == 201
    schedule = created.json()
    assert schedule["cron"] == "*/5 * * * *"
    assert schedule["is_enabled"] is True

    interval = await client.post(
        f"{API}/workflows/{workflow_id}/schedules",
        headers=auth(OPERATOR_KEY),
        json={"interval_seconds": 60},
    )
    assert interval.status_code == 201

    listed = await client.get(f"{API}/workflows/{workflow_id}/schedules", headers=auth(VIEWER_KEY))
    assert listed.status_code == 200
    assert len(listed.json()) == 2

    invalid_cron = await client.post(
        f"{API}/workflows/{workflow_id}/schedules",
        headers=auth(OPERATOR_KEY),
        json={"cron": "not-a-cron"},
    )
    assert invalid_cron.status_code == 422

    empty_trigger = await client.post(f"{API}/workflows/{workflow_id}/schedules", headers=auth(OPERATOR_KEY), json={})
    assert empty_trigger.status_code == 422

    deleted = await client.delete(f"{API}/schedules/{schedule['id']}", headers=auth(OPERATOR_KEY))
    assert deleted.status_code == 204

    remaining = await client.get(f"{API}/workflows/{workflow_id}/schedules", headers=auth(VIEWER_KEY))
    assert len(remaining.json()) == 1


async def test_pagination_parameters_are_validated(client):
    invalid = await client.get(f"{API}/workflows?limit=0", headers=auth(VIEWER_KEY))
    assert invalid.status_code == 422
    too_large = await client.get(f"{API}/workflows?limit=201", headers=auth(VIEWER_KEY))
    assert too_large.status_code == 422
