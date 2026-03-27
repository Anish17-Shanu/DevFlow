# API Guide

## Workflow Endpoints

- `POST /api/workflows`
  Creates a workflow DAG from a name plus task definitions.
- `GET /api/workflows`
  Lists workflows with their task definitions.
- `GET /api/workflows/{workflow_id}`
  Fetches a specific workflow.

## Execution Endpoints

- `POST /api/workflows/{workflow_id}/run`
  Creates an execution and enqueues its ready tasks.
- `GET /api/executions/{execution_id}`
  Returns the execution status and timestamps.
- `GET /api/executions/{execution_id}/tasks`
  Returns execution task state, retry count, assigned worker, and errors.
- `GET /api/executions/{execution_id}/logs`
  Returns execution logs ordered by creation time.

## Monitoring Endpoints

- `GET /api/queue/status`
  Returns queue depth, in-flight jobs, processed totals, backend name, and durability status.
- `GET /api/workers/status`
  Returns worker heartbeat snapshots and active execution/task assignments.
- `GET /api/system/snapshot`
  Returns queue and worker monitoring data in one payload.

## Health Endpoints

- `GET /health`
  Basic service metadata and liveness metadata.
- `GET /health/live`
  Lightweight liveness check suitable for container probes.
- `GET /health/ready`
  Readiness check with database status, worker health summary, and queue status.

## Websocket Endpoint

- `GET /ws/executions/{execution_id}`
  Opens a websocket stream for execution update events.

## Example Workflow Payload

```json
{
  "name": "Nightly ingestion",
  "tasks": [
    {
      "name": "extract",
      "dependencies": [],
      "config": {
        "duration_ms": 1000,
        "priority": 5,
        "max_retries": 1
      }
    },
    {
      "name": "transform",
      "dependencies": ["extract"],
      "config": {
        "duration_ms": 1200,
        "backoff_seconds": 1,
        "max_retries": 2
      }
    }
  ]
}
```
