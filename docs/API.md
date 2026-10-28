# API Guide

Generated from the OpenAPI schema by `scripts/generate_api_docs.py`.
Run the script (or `python scripts/generate_api_docs.py --check` in CI) after changing routes.

Base URL: `/` · API version `2.0.0`

## Authentication

Send a scoped API key in the `X-API-Key` header (or `Authorization: Bearer <key>`).
Roles: `viewer` (read), `operator` (run/cancel/edit), `admin` (keys, secrets, webhooks, archive).

## Errors

Every error uses one envelope:

```json
{"code": "forbidden", "message": "Readable summary.", "request_id": "…", "details": null}
```

`X-Request-ID` is echoed on every response and included in structured logs.

## Versioning

Routes live under `/api/v1`. Additive changes ship in place; breaking changes require a new
prefix and a deprecation window of at least one minor release. `/health*` and `/metrics` are
unversioned operational endpoints.

## Endpoints

### `GET /api/v1/audit`

List Audit

| Parameter | In | Required | Type |
| --- | --- | --- | --- |
| `limit` | query | no | integer |
| `offset` | query | no | integer |

Responses: 200 Successful Response, 401 Unauthorized, 422 Validation Error, 429 Too Many Requests

### `GET /api/v1/auth/keys`

List Keys

Responses: 200 Successful Response, 401 Unauthorized, 429 Too Many Requests

### `POST /api/v1/auth/keys`

Create Key

Request body (`application/json`): `ApiKeyCreate`

Responses: 201 Successful Response, 401 Unauthorized, 422 Validation Error, 429 Too Many Requests

### `DELETE /api/v1/auth/keys/{key_id}`

Revoke Key

| Parameter | In | Required | Type |
| --- | --- | --- | --- |
| `key_id` | path | yes | string |

Responses: 204 Successful Response, 401 Unauthorized, 422 Validation Error, 429 Too Many Requests

### `GET /api/v1/auth/me`

Me

Responses: 200 Successful Response, 401 Unauthorized, 429 Too Many Requests

### `GET /api/v1/diagnostics`

Diagnostics

Responses: 200 Successful Response, 401 Unauthorized, 429 Too Many Requests

### `GET /api/v1/executions`

List Executions

| Parameter | In | Required | Type |
| --- | --- | --- | --- |
| `limit` | query | no | integer |
| `offset` | query | no | integer |
| `status` | query | no | object |
| `workflow_id` | query | no | object |

Responses: 200 Successful Response, 401 Unauthorized, 422 Validation Error, 429 Too Many Requests

### `GET /api/v1/executions/{execution_id}`

Get Execution

| Parameter | In | Required | Type |
| --- | --- | --- | --- |
| `execution_id` | path | yes | string |

Responses: 200 Successful Response, 401 Unauthorized, 422 Validation Error, 429 Too Many Requests

### `POST /api/v1/executions/{execution_id}/cancel`

Cancel Execution

| Parameter | In | Required | Type |
| --- | --- | --- | --- |
| `execution_id` | path | yes | string |

Responses: 200 Successful Response, 401 Unauthorized, 422 Validation Error, 429 Too Many Requests

### `GET /api/v1/executions/{execution_id}/logs`

Get Execution Logs

| Parameter | In | Required | Type |
| --- | --- | --- | --- |
| `execution_id` | path | yes | string |
| `limit` | query | no | integer |
| `offset` | query | no | integer |
| `after` | query | no | object |

Responses: 200 Successful Response, 401 Unauthorized, 422 Validation Error, 429 Too Many Requests

### `POST /api/v1/executions/{execution_id}/retry`

Retry Execution

| Parameter | In | Required | Type |
| --- | --- | --- | --- |
| `execution_id` | path | yes | string |

Responses: 200 Successful Response, 401 Unauthorized, 422 Validation Error, 429 Too Many Requests

### `GET /api/v1/executions/{execution_id}/tasks`

Get Execution Tasks

| Parameter | In | Required | Type |
| --- | --- | --- | --- |
| `execution_id` | path | yes | string |

Responses: 200 Successful Response, 401 Unauthorized, 422 Validation Error, 429 Too Many Requests

### `POST /api/v1/executions/{execution_id}/tasks/{task_identifier}/retry`

Retry Task

| Parameter | In | Required | Type |
| --- | --- | --- | --- |
| `execution_id` | path | yes | string |
| `task_identifier` | path | yes | string |

Responses: 200 Successful Response, 401 Unauthorized, 422 Validation Error, 429 Too Many Requests

### `POST /api/v1/executions/{execution_id}/tasks/{task_identifier}/skip`

Skip Task

| Parameter | In | Required | Type |
| --- | --- | --- | --- |
| `execution_id` | path | yes | string |
| `task_identifier` | path | yes | string |

Responses: 200 Successful Response, 401 Unauthorized, 422 Validation Error, 429 Too Many Requests

### `GET /api/v1/queue/dead-letters`

List Dead Letters

| Parameter | In | Required | Type |
| --- | --- | --- | --- |
| `limit` | query | no | integer |
| `offset` | query | no | integer |

Responses: 200 Successful Response, 401 Unauthorized, 422 Validation Error, 429 Too Many Requests

### `POST /api/v1/queue/dead-letters/{job_id}/replay`

Replay Dead Letter

| Parameter | In | Required | Type |
| --- | --- | --- | --- |
| `job_id` | path | yes | string |

Responses: 200 Successful Response, 401 Unauthorized, 422 Validation Error, 429 Too Many Requests

### `GET /api/v1/queue/status`

Get Queue Status

Responses: 200 Successful Response, 401 Unauthorized, 429 Too Many Requests

### `DELETE /api/v1/schedules/{schedule_id}`

Delete Schedule

| Parameter | In | Required | Type |
| --- | --- | --- | --- |
| `schedule_id` | path | yes | string |

Responses: 204 Successful Response, 401 Unauthorized, 422 Validation Error, 429 Too Many Requests

### `GET /api/v1/secrets`

List Secrets

Responses: 200 Successful Response, 401 Unauthorized, 429 Too Many Requests

### `POST /api/v1/secrets`

Create Secret

Request body (`application/json`): `SecretCreate`

Responses: 201 Successful Response, 401 Unauthorized, 422 Validation Error, 429 Too Many Requests

### `DELETE /api/v1/secrets/{name}`

Delete Secret

| Parameter | In | Required | Type |
| --- | --- | --- | --- |
| `name` | path | yes | string |

Responses: 204 Successful Response, 401 Unauthorized, 422 Validation Error, 429 Too Many Requests

### `GET /api/v1/system/snapshot`

Get System Snapshot

Responses: 200 Successful Response, 401 Unauthorized, 429 Too Many Requests

### `GET /api/v1/webhooks`

List Webhooks

Responses: 200 Successful Response, 401 Unauthorized, 429 Too Many Requests

### `POST /api/v1/webhooks`

Create Webhook

Request body (`application/json`): `WebhookCreate`

Responses: 201 Successful Response, 401 Unauthorized, 422 Validation Error, 429 Too Many Requests

### `GET /api/v1/webhooks/deliveries`

List Deliveries

| Parameter | In | Required | Type |
| --- | --- | --- | --- |
| `limit` | query | no | integer |
| `offset` | query | no | integer |

Responses: 200 Successful Response, 401 Unauthorized, 422 Validation Error, 429 Too Many Requests

### `DELETE /api/v1/webhooks/{webhook_id}`

Delete Webhook

| Parameter | In | Required | Type |
| --- | --- | --- | --- |
| `webhook_id` | path | yes | string |

Responses: 204 Successful Response, 401 Unauthorized, 422 Validation Error, 429 Too Many Requests

### `GET /api/v1/workers/status`

Get Workers Status

Responses: 200 Successful Response, 401 Unauthorized, 429 Too Many Requests

### `GET /api/v1/workflows`

List Workflows

| Parameter | In | Required | Type |
| --- | --- | --- | --- |
| `limit` | query | no | integer |
| `offset` | query | no | integer |
| `include_archived` | query | no | boolean |

Responses: 200 Successful Response, 401 Unauthorized, 422 Validation Error, 429 Too Many Requests

### `POST /api/v1/workflows`

Create Workflow

Request body (`application/json`): `WorkflowCreate`

Responses: 201 Successful Response, 401 Unauthorized, 422 Validation Error, 429 Too Many Requests

### `POST /api/v1/workflows/import`

Import Workflow

Request body (`application/json`): `WorkflowCreate`

Responses: 201 Successful Response, 401 Unauthorized, 422 Validation Error, 429 Too Many Requests

### `GET /api/v1/workflows/templates`

List Templates

Responses: 200 Successful Response, 401 Unauthorized, 429 Too Many Requests

### `GET /api/v1/workflows/{workflow_id}`

Get Workflow

| Parameter | In | Required | Type |
| --- | --- | --- | --- |
| `workflow_id` | path | yes | string |

Responses: 200 Successful Response, 401 Unauthorized, 422 Validation Error, 429 Too Many Requests

### `PATCH /api/v1/workflows/{workflow_id}`

Update Workflow

| Parameter | In | Required | Type |
| --- | --- | --- | --- |
| `workflow_id` | path | yes | string |

Request body (`application/json`): `WorkflowUpdate`

Responses: 200 Successful Response, 401 Unauthorized, 422 Validation Error, 429 Too Many Requests

### `DELETE /api/v1/workflows/{workflow_id}`

Delete Workflow

| Parameter | In | Required | Type |
| --- | --- | --- | --- |
| `workflow_id` | path | yes | string |

Responses: 204 Successful Response, 401 Unauthorized, 422 Validation Error, 429 Too Many Requests

### `POST /api/v1/workflows/{workflow_id}/clone`

Clone Workflow

| Parameter | In | Required | Type |
| --- | --- | --- | --- |
| `workflow_id` | path | yes | string |

Request body (`application/json`): `WorkflowCloneRequest`

Responses: 201 Successful Response, 401 Unauthorized, 422 Validation Error, 429 Too Many Requests

### `GET /api/v1/workflows/{workflow_id}/export`

Export Workflow

| Parameter | In | Required | Type |
| --- | --- | --- | --- |
| `workflow_id` | path | yes | string |

Responses: 200 Successful Response, 401 Unauthorized, 422 Validation Error, 429 Too Many Requests

### `GET /api/v1/workflows/{workflow_id}/revisions`

List Revisions

| Parameter | In | Required | Type |
| --- | --- | --- | --- |
| `workflow_id` | path | yes | string |

Responses: 200 Successful Response, 401 Unauthorized, 422 Validation Error, 429 Too Many Requests

### `POST /api/v1/workflows/{workflow_id}/run`

Run Workflow

| Parameter | In | Required | Type |
| --- | --- | --- | --- |
| `workflow_id` | path | yes | string |
| `Idempotency-Key` | header | no | object |

Responses: 200 Successful Response, 401 Unauthorized, 422 Validation Error, 429 Too Many Requests

### `GET /api/v1/workflows/{workflow_id}/schedules`

List Schedules

| Parameter | In | Required | Type |
| --- | --- | --- | --- |
| `workflow_id` | path | yes | string |

Responses: 200 Successful Response, 401 Unauthorized, 422 Validation Error, 429 Too Many Requests

### `POST /api/v1/workflows/{workflow_id}/schedules`

Create Schedule

| Parameter | In | Required | Type |
| --- | --- | --- | --- |
| `workflow_id` | path | yes | string |

Request body (`application/json`): `ScheduleCreate`

Responses: 201 Successful Response, 401 Unauthorized, 422 Validation Error, 429 Too Many Requests

### `GET /health`

Health

Responses: 200 Successful Response, 401 Unauthorized, 429 Too Many Requests

### `GET /health/live`

Live Health

Responses: 200 Successful Response, 401 Unauthorized, 429 Too Many Requests

### `GET /health/ready`

Readiness

Responses: 200 Successful Response, 401 Unauthorized, 429 Too Many Requests

## WebSocket streaming

`GET /ws/executions/{execution_id}?api_key=<key>` upgrades to a WebSocket. The socket is
authenticated per execution and closed with code `1008` for missing keys, invalid keys,
unknown executions, or cross-tenant access. Send the text frame `subscribe` to receive
event notifications; clients should fall back to polling `/logs` while disconnected.

## Schemas

- **ApiKeyCreate**
- **ApiKeyCreatedResponse**
- **ApiKeyResponse**
- **DeadLetterJobResponse**
- **DeadLetterListResponse**
- **DiagnosticsResponse**
- **ErrorResponse**
- **ExecutionListResponse**
- **ExecutionLogListResponse**
- **ExecutionLogResponse**
- **ExecutionResponse**
- **ExecutionStatus**
- **ExecutionTaskResponse**
- **HTTPValidationError**
- **HealthResponse**
- **MeResponse**
- **QueueStatusResponse**
- **ReadinessResponse**
- **ScheduleCreate**
- **ScheduleResponse**
- **SecretCreate**
- **SecretResponse**
- **SystemSnapshotResponse**
- **TaskConfig**
- **TaskState**
- **ValidationError**
- **WebhookCreate**
- **WebhookResponse**
- **WorkerStatusResponse**
- **WorkflowCloneRequest**
- **WorkflowCreate**
- **WorkflowListResponse**
- **WorkflowResponse**
- **WorkflowRevisionResponse**
- **WorkflowTaskCreate**
- **WorkflowTaskResponse**
- **WorkflowTemplateResponse**
- **WorkflowUpdate**
