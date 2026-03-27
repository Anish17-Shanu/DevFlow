# Deployment Guide

## Requirements

- Docker Engine with Compose support.
- A host or platform capable of running at least:
  - one API container
  - one worker container
  - one PostgreSQL container or managed PostgreSQL service
  - one static frontend container

## Local Production-Style Deployment

```bash
docker compose up --build
```

This stack starts:

- `postgres`
- `api`
- `worker`
- `frontend`

## Production Recommendations

- Use PostgreSQL, not SQLite, in deployed environments.
- Run at least one dedicated worker process separate from the API process.
- Set `DEVFLOW_INLINE_WORKERS_ENABLED=false` for deployed API instances.
- Configure `DEVFLOW_CORS_ORIGINS` to the real frontend origin.
- Keep `DEVFLOW_DOCS_ENABLED=false` in production unless interactive docs are intentionally public.
- Scale the `worker` service independently based on queue depth and execution volume.

## Environment Checklist

- Set `DEVFLOW_ENVIRONMENT=production`.
- Set `DEVFLOW_DATABASE_URL` to a persistent PostgreSQL database.
- Set `DEVFLOW_CORS_ORIGINS` to the deployed frontend URL.
- Set `DEVFLOW_WORKER_COUNT` based on available CPU and expected concurrency.
- Review `DEVFLOW_QUEUE_LEASE_SECONDS` so it is comfortably longer than heartbeat renewal cadence.

## Health Checks

- Liveness: `GET /health/live`
- Readiness: `GET /health/ready`

If readiness reports degraded workers, inspect worker logs and worker heartbeat records before routing traffic or starting heavy workflow loads.

## Rolling Updates

Suggested order:

1. Deploy database changes first.
2. Deploy API instances.
3. Deploy worker instances.
4. Deploy frontend last.

This order keeps the websocket and monitoring paths aligned with the current execution schema.
