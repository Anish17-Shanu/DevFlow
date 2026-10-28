# Operations Runbook

On-call reference for DevFlow. Alert annotations in
[deploy/observability/alerts.yml](../deploy/observability/alerts.yml) link to the
sections below.

## Service level objectives

| SLI | Target | Measurement |
| --- | --- | --- |
| API availability | 99.9% monthly | non-5xx responses / all responses on `/api/v1` and `/health` |
| API latency (p95) | < 1 s reads, < 2 s writes | `devflow_http_request_duration_seconds` |
| Queue wait (p95) | < 60 s | `devflow_task_wait_seconds` |
| Execution success | > 95% excluding user-authored failures | `devflow_executions_total` |
| Fresh worker heartbeat | at least one worker within 30 s | `devflow_workers_online` |

Error budget policy: when 50% of the monthly budget is spent, freeze non-critical
releases and prioritize reliability work. At 100%, only fixes and rollbacks ship.

Recovery objectives for PostgreSQL: **RPO 15 minutes** with continuous WAL archiving,
**RTO 1 hour** for a restore into a new instance. Daily logical backups alone give an
RPO of 24 hours; use them for accidental deletion, and rely on PITR for infrastructure
loss.

## First response

1. Check `GET /health/ready` on every API replica.
2. Check the [Grafana overview](../deploy/observability/grafana-dashboard.json).
3. Confirm workers are heartbeating: `GET /api/v1/workers/status` with an admin key.
4. Look for recent deploys or migrations in the release history.
5. If the blast radius is growing, roll back the last release before deep debugging.

Useful commands:

```bash
# API and worker logs (Compose)
docker compose logs --since 15m api worker

# Queue and worker snapshot
curl -fsS -H "X-API-Key: $DEVFLOW_ADMIN_KEY" http://127.0.0.1:8000/api/v1/queue/status
curl -fsS -H "X-API-Key: $DEVFLOW_ADMIN_KEY" http://127.0.0.1:8000/api/v1/workers/status

# Dead letters
curl -fsS -H "X-API-Key: $DEVFLOW_ADMIN_KEY" "http://127.0.0.1:8000/api/v1/queue/dead-letters?limit=20"

# Recent structured logs for one request or execution id
docker compose logs api | grep '"request_id"'
```

## High API error rate

1. Split 5xx by route: `sum by (path) (rate(devflow_http_requests_total{status=~"5.."}[5m]))`.
2. Check the latest deploy. If errors started within 15 minutes of a release, roll back.
3. Inspect structured logs for `Unhandled error` with the corresponding `request_id`.
4. If the database is the source, check `pg_stat_activity` for locks and long transactions.
5. If a single tenant is causing load, rate limit or disable its key (admin API).

## High API latency

1. Identify the slow route from the latency panel.
2. For `/executions*`, check queue and worker saturation; list queries can be slow when a
   tenant has many executions (review retention).
3. Check connection pool wait (`sqlalchemy.pool` logs) and raise pool size only after
   checking database connection limits.
4. If the event loop is blocked, capture a stack dump and look for synchronous calls in
   request handlers.

## Worker heartbeat loss

1. `docker compose ps` / `kubectl get pods -l app.kubernetes.io/name=worker`.
2. Worker health is file-based: the container probe runs
   `python -m backend.worker_healthcheck`. A stale heartbeat means the event loop is
   blocked, the process is dead, or `/tmp` is not writable.
3. Restart the worker. Jobs with unexpired leases are retried after the lease expires;
   the watchdog finalizes executions whose workers never return.
4. If restarts loop, read worker logs for a poison job and quarantine it from the
   dead-letter view.

## Queue backlog

1. Compare `devflow_queue_depth` with worker CPU. Add worker replicas if CPU is low.
2. Check for delayed jobs (`devflow_queue_delayed`) and cron schedules firing together.
3. Inspect per-workflow concurrency limits: a single workflow cannot exceed
   `DEVFLOW_MAX_CONCURRENT_TASKS_PER_WORKFLOW` leased tasks.
4. If one workflow floods the queue, cancel or archive it; priority aging prevents
   newest low-priority work from completely starving older work.
5. If backlog persists with healthy workers, profile task handlers (slow HTTP calls,
   retries with backoff) using `devflow_task_duration_seconds`.

## Dead-letter jobs

1. List dead letters with the admin API; each row includes attempts and the last error.
2. Fix the root cause (bad config, unreachable endpoint, expired secret).
3. Replay from the UI (Operations → Dead letters) or
   `POST /api/v1/queue/dead-letters/{job_id}/replay`.
4. Resolve entries that should not be retried so the gauge returns to zero.

Replay re-enqueues with a fresh attempt counter. Do not bulk-replay during an incident
until the underlying dependency is healthy.

## High execution failure rate

1. Group failures by workflow and task error message.
2. If failures are user-authored (HTTP 4xx targets, invalid config), notify the tenant
   rather than treating it as a platform incident.
3. If failures are environmental (network, DNS, secrets), fix the dependency, then retry
   failed executions from the UI.
4. A task that repeatedly kills workers is dead-lettered after
   `DEVFLOW_QUEUE_POISON_MAX_ATTEMPTS`.

## Deploy and rollback

1. Run migrations (`migrate` service or pre-sync Job) and confirm it exits 0.
2. Roll API first, then workers, then the web image. Kubernetes does this automatically
   through rollouts and pod disruption budgets.
3. Verify `/health/ready`, worker heartbeats, and one golden-path execution.
4. Rollback: redeploy the previous image tag. Do **not** downgrade the database without a
   tested down migration; migrations are forward-only in production.

## Backup and restore drill

Monthly drill:

```bash
scripts/backup_postgres.sh backups
# Inspect the archive
docker compose exec -T postgres pg_restore --list < backups/devflow-<timestamp>.dump

# Restore into a scratch database (never production first)
docker compose exec -T postgres psql -U devflow -d postgres -c 'CREATE DATABASE devflow_restore;'
docker compose exec -T postgres pg_restore -U devflow -d devflow_restore --no-owner --no-privileges < backups/devflow-<timestamp>.dump
docker compose exec -T postgres psql -U devflow -d devflow_restore -c 'SELECT count(*) FROM executions;'
```

Record the restore duration and row counts. A drill passes when the archive restores
without errors, the API can read the restored data, and elapsed time is within RTO.

## Escalation

| Severity | Who | Response |
| --- | --- | --- |
| Page (availability, data loss risk) | on-call engineer | acknowledge in 5 min, mitigate in 30 min |
| Ticket (SLO burn, backlog) | on-call engineer during business hours | same day |
| Security | security contact per [SECURITY.md](../SECURITY.md) | follow the security policy |

Escalate to the platform lead when a mitigation requires a schema change, data restore,
or disabling a tenant. Document the incident timeline and follow up with an action item
in [ROADMAP.md](../ROADMAP.md) using a `FIX-` ID when code changes are needed.
