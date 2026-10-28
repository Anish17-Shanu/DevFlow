# DevFlow

## Creator

This project was created, written, and maintained by **Anish Kumar**.
All primary documentation in this README is presented as the work of **Anish Kumar**.

DevFlow is a production-style distributed workflow and job processing engine built around a strict `Web -> API -> Queue -> Worker -> DB -> UI` architecture. Teams can define DAG-based workflows, execute them asynchronously, inspect task lifecycles in real time, and monitor queue or worker health from a React control plane.

> **Project status:** not yet fully production-grade. See [ROADMAP.md](ROADMAP.md) for the living checklist of completed hardening work and remaining gaps (auth, migrations, observability, HA).

## Highlights

- FastAPI backend with workflow, execution, monitoring, and websocket endpoints.
- Durable database-backed queue with leased jobs and stale-lease recovery.
- Dedicated worker process model for multi-process deployment.
- PostgreSQL-ready runtime plus SQLite support for local development.
- Live execution refresh with websocket delivery and polling fallback.
- Health and readiness probes for container and platform deployments.
- Production-oriented Docker Compose stack with API, worker, PostgreSQL, and static frontend hosting.
- Automated backend tests plus frontend production build verification.

## Architecture

- [Architecture Guide](docs/ARCHITECTURE.md)
- [API Guide](docs/API.md)
- [Deployment Guide](docs/DEPLOYMENT.md)
- [Operations Runbook](docs/OPERATIONS.md)
- [Troubleshooting Guide](docs/TROUBLESHOOTING.md)
- [Contributing Guide](docs/CONTRIBUTING.md)
- [Production Readiness Roadmap](ROADMAP.md)

## Core API

- `POST /api/workflows`
- `GET /api/workflows`
- `GET /api/workflows/{id}`
- `POST /api/workflows/{id}/run`
- `GET /api/executions/{id}`
- `GET /api/executions/{id}/tasks`
- `GET /api/executions/{id}/logs`
- `GET /api/queue/status`
- `GET /api/workers/status`
- `GET /api/system/snapshot`
- `GET /health`
- `GET /health/live`
- `GET /health/ready`
- `GET /ws/executions/{id}`

## Local Development

Requires **Python 3.12, 3.13, or 3.14** and **Node.js 20+**. The dependency pins are verified against all three Python versions in CI.

### Backend

```bash
cd DevFlow
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS / Linux
pip install -r backend/requirements-dev.txt
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

### Dedicated Worker

```bash
cd DevFlow
.venv\Scripts\activate
python -m backend.worker_main
```

### Frontend

```bash
cd DevFlow/frontend
npm install
npm run dev
```

## Docker Deployment

```bash
docker compose up --build
```

Default container endpoints:

- Frontend: `http://localhost:8080`
- API: `http://localhost:8000`
- Liveness: `http://localhost:8000/health/live`
- Readiness: `http://localhost:8000/health/ready`

## Environment Variables

Copy [.env.example](.env.example) to `.env` and adjust values as needed.

- `DEVFLOW_ENVIRONMENT`
- `DEVFLOW_APP_VERSION`
- `DEVFLOW_DATABASE_URL`
- `DEVFLOW_WORKER_COUNT`
- `DEVFLOW_WORKER_POLL_INTERVAL_MS`
- `DEVFLOW_WORKER_HEARTBEAT_INTERVAL_SECONDS`
- `DEVFLOW_INLINE_WORKERS_ENABLED`
- `DEVFLOW_CORS_ORIGINS` (required in production)
- `DEVFLOW_DOCS_ENABLED`
- `DEVFLOW_LOG_LEVEL`
- `DEVFLOW_QUEUE_LEASE_SECONDS`
- `DEVFLOW_REALTIME_POLL_INTERVAL_MS`
- `DEVFLOW_MAX_REQUEST_BODY_BYTES`
- `POSTGRES_PASSWORD` (Docker Compose only; defaults to `devflow` for local use)

## Verification

```bash
pip install -r backend/requirements-dev.txt
ruff check backend
python -m pytest
cd frontend
npm ci
npm run build
```

## Sample Workflow Payload

```json
{
  "name": "Nightly Payments DAG",
  "tasks": [
    {
      "name": "extract",
      "dependencies": [],
      "config": {
        "duration_ms": 900,
        "priority": 2,
        "max_retries": 1
      }
    },
    {
      "name": "transform",
      "dependencies": ["extract"],
      "config": {
        "duration_ms": 1200,
        "fail_first_n": 1,
        "max_retries": 2,
        "backoff_seconds": 1
      }
    },
    {
      "name": "load",
      "dependencies": ["transform"],
      "config": {
        "duration_ms": 700
      }
    }
  ]
}
```