# Operations Guide

Day-to-day operator tasks for DevFlow. Incident detection, mitigation, escalation, and restore drills live in the [Runbook](RUNBOOK.md); release gates live in the [Production Checklist](PRODUCTION_CHECKLIST.md).

## Runtime components

- **API** — serves HTTP and websocket traffic, runs the outbox notifier, watchdog, scheduler, retention, and optionally inline workers. On PostgreSQL it joins the realtime `LISTEN/NOTIFY` bus so websocket clients receive execution updates from every replica.
- **Worker** — leases queue jobs and executes task handlers. Each process writes a heartbeat file used by its container health check.
- **PostgreSQL** — stores workflows, revisions, executions, tasks, logs, queue jobs, dead letters, outbox events, webhooks, audit events, and worker records.
- **Frontend** — static React control plane served by unprivileged nginx, proxying `/api`, `/ws`, `/health`, and `/metrics` to the API.

## Health expectations

| Endpoint | Healthy result | Use |
| --- | --- | --- |
| `GET /health/live` | `status: ok` | Container restart decisions |
| `GET /health/ready` | `status: ok`, database `ok`, workers `running`, queue durable | Traffic routing |
| `GET /metrics` | Prometheus text | Dashboards and alerts |
| Worker health check | `python -m backend.worker_healthcheck` exits 0 | Container liveness for workers |

`/health/ready` reports `degraded` in production when no worker is running or the queue reports unhealthy. Do not route user traffic to a degraded API.

## Common operator tasks

### Start the local production-style stack

```bash
export POSTGRES_PASSWORD=...
export DEVFLOW_BOOTSTRAP_API_KEY=...
export DEVFLOW_SECRET_ENCRYPTION_KEY=...
docker compose up --build
```

The Compose stack runs PostgreSQL, a one-off migration job, the API, a dedicated worker, and the frontend. See [DEPLOYMENT.md](DEPLOYMENT.md) for TLS and Kubernetes.

### Run checks

```bash
ruff check backend migrations
ruff format --check backend migrations
python -m pytest --cov=backend
python scripts/generate_api_docs.py --check
cd frontend && npm run test:coverage && npm run build
```

PostgreSQL integration: set `DEVFLOW_TEST_POSTGRES_URL=postgresql+asyncpg://…` before `pytest`.

### Inspect logs

```bash
docker compose logs -f api
docker compose logs -f worker
docker compose logs -f postgres
```

Logs are JSON in deployed environments. Filter by `request_id` to follow one HTTP request; `execution_id`, `task_id`, and `worker_id` are attached where available.

### Queue and worker status

```bash
curl -H "X-API-Key: $KEY" $API/api/v1/queue/status
curl -H "X-API-Key: $KEY" $API/api/v1/workers/status
curl -H "X-API-Key: $KEY" $API/api/v1/system/snapshot
curl -H "X-API-Key: $KEY" $API/api/v1/diagnostics
```

Track `queued_jobs`, `delayed_jobs`, `in_flight_jobs`, `dead_letter_jobs`, `total_processed`, and `healthy`. Growing queue depth with low worker activity means workers are down, unhealthy, or under-provisioned.

### Dead letters

```bash
curl -H "X-API-Key: $KEY" "$API/api/v1/queue/dead-letters?limit=50"
curl -X POST -H "X-API-Key: $KEY" "$API/api/v1/queue/dead-letters/$JOB_ID/replay"
```

Inspect the job's execution and logs before replaying. Poison jobs are quarantined after the configured attempt limit (`DEVFLOW_QUEUE_POISON_MAX_ATTEMPTS`).

### Scale workers

```bash
docker compose up --build --scale worker=3
```

Kubernetes uses the worker Deployment plus HPA (CPU) or KEDA (queue lag). Scaling workers does not require an API restart; workers register with unique IDs.

### Drain and restart a worker

Workers stop claiming on shutdown and finish in-flight tasks within `DEVFLOW_WORKER_SHUTDOWN_GRACE_SECONDS`. In Kubernetes, the worker termination grace period is 45 seconds. Do not force-kill workers during a deploy; the watchdog will recover lost work but with extra retries.

### Backups

```bash
# Compose deployment (runs pg_dump inside the postgres container)
scripts/backup_postgres.sh backups
scripts/restore_postgres.sh backups/devflow-YYYYmmddTHHMMSSZ.dump --yes
```

For Kubernetes, run `pg_dump`/`pg_restore` against the PostgreSQL service from a maintenance pod or your provider's managed-backup tooling. Test restores on a schedule. See the [Runbook](RUNBOOK.md#backup-and-restore-drill) for the drill and RPO/RTO targets.

### Capacity checks

```bash
python scripts/load_test.py --base-url http://127.0.0.1:8000 --mode read --concurrency 20
python scripts/load_test.py --base-url http://127.0.0.1:8000 --mode run --run-executions 100 --concurrency 10
```

Record results with the release evidence. Reference measurements and sizing guidance are in [CAPACITY.md](CAPACITY.md).

## Alerts

Load [deploy/observability/alerts.yml](../deploy/observability/alerts.yml) into Prometheus and [deploy/observability/grafana-dashboard.json](../deploy/observability/grafana-dashboard.json) into Grafana. Every alert links to a section of the [Runbook](RUNBOOK.md). The highest-urgency signals are worker heartbeat loss, queue backlog, dead-letter growth, and execution failure rate.

## Scheduled maintenance

- Retention runs hourly by default and removes expired logs, executions, queue records, and worker rows. Review the first run in staging before enabling in production.
- Verify backups daily; run the restore drill at least quarterly.
- Rotate API keys and the secret encryption key on your organization's schedule. Key rotation requires re-encrypting stored secrets; see [SECURITY.md](../SECURITY.md).
- Review dead letters weekly and add a regression test or handler fix before replaying in bulk.
