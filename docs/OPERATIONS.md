# Operations Runbook

## Runtime Components

- API process: serves HTTP and websocket traffic.
- Worker process: leases jobs and executes tasks.
- Database: stores workflows, executions, logs, queue jobs, and worker records.
- Frontend: provides the control plane UI.

## Normal Health Expectations

- `/health/live` should return `ok`.
- `/health/ready` should return `ok`.
- Worker state should usually be `idle` or `running`.
- Queue durability should report `true`.

## Common Operator Tasks

### Check backend tests

```bash
python -m pytest
```

### Check frontend production build

```bash
cd frontend
npm run build
```

### Start local production-style stack

```bash
docker compose up --build
```

### Inspect logs

```bash
docker compose logs api
docker compose logs worker
docker compose logs frontend
docker compose logs postgres
```

### Scale workers

```bash
docker compose up --build --scale worker=3
```

## Queue Observability

Important monitoring fields:

- `queued_jobs`
- `delayed_jobs`
- `in_flight_jobs`
- `total_enqueued`
- `total_processed`
- `is_durable`

Growing `queued_jobs` with low worker activity usually means workers are down, unhealthy, or under-provisioned.

## Worker Observability

Important worker fields:

- `state`
- `processed_jobs`
- `failed_jobs`
- `last_seen_at`
- `last_error`

If `last_seen_at` stops moving, the worker is stale or offline.
