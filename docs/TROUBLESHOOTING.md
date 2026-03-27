# Troubleshooting

## API Readiness Is Degraded

Check:

- database connectivity
- worker container status
- worker heartbeat freshness
- queue stats from `/api/queue/status`

## Queue Jobs Are Stuck

Possible causes:

- no worker processes are running
- workers cannot reach the database
- lease duration is too short for task runtime and renewal is failing

Actions:

1. Inspect worker logs.
2. Check `/api/workers/status`.
3. Check `/health/ready`.

## Frontend Loads But Data Does Not Refresh

Check:

- `VITE_API_BASE_URL`
- `VITE_WS_BASE_URL`
- browser console websocket errors
- API health endpoints

The UI will fall back to polling if websocket delivery fails, so a total lack of updates usually means API connectivity problems rather than websocket-only issues.

## Existing Database Fails After Upgrade

DevFlow includes a lightweight startup migration for the `executions.updated_at` column used by the execution notifier. If startup still fails:

1. confirm the database user has schema migration privileges
2. inspect API logs during startup
3. re-run against a fresh local database to separate migration issues from runtime issues

## Docker Build Fails

Check:

- Docker daemon is running
- network access for pulling base images
- `frontend/package-lock.json` matches `frontend/package.json`
- enough disk space is available for image layers
