# DevFlow

## Creator

This project was created, written, and maintained by **Anish Kumar (ANISH KUMAR)**.
All primary documentation in this README is presented as the work of **Anish Kumar**.

DevFlow is a production-style distributed workflow and job processing engine built around a strict `Web -> API -> Queue -> Worker -> DB -> UI` architecture. It lets teams define DAG-based workflows, execute them asynchronously, observe task lifecycles in real time, and inspect queue or worker health from a React dashboard.

## Architecture

- `backend/main.py`: FastAPI application bootstrap, lifecycle hooks, and route registration.
- `backend/api`: HTTP and WebSocket delivery layer.
- `backend/controllers`: Thin controller layer for workflows, executions, and monitoring.
- `backend/services`: DAG validation, workflow creation, execution orchestration, logging, realtime broadcast, and seed loading.
- `backend/queue`: Custom in-memory queue with FIFO ordering, delay support, priorities, retries, and in-flight tracking.
- `backend/workers`: Stateless worker runtime that polls the queue concurrently.
- `frontend/src/pages`: Workflow builder, execution dashboard, logs view, and worker monitor.

## Features

- DAG validation with cycle detection.
- Async workflow execution with dependency-aware scheduling.
- Task states: `pending`, `queued`, `running`, `success`, `failed`, `retrying`.
- Exponential backoff retries driven by task config.
- Parallel workers polling a shared queue abstraction.
- Live execution refresh over WebSocket plus polling fallback.
- SQLite default development database with PostgreSQL-ready SQLAlchemy setup.
- Sample seeded workflows for immediate exploration.

## API

- `POST /api/workflows`
- `GET /api/workflows`
- `GET /api/workflows/{id}`
- `POST /api/workflows/{id}/run`
- `GET /api/executions/{id}`
- `GET /api/executions/{id}/tasks`
- `GET /api/executions/{id}/logs`
- `GET /api/queue/status`
- `GET /api/workers/status`
- `GET /health`
- `GET /ws/executions/{id}`

## Local Setup

### Backend

```bash
cd DevFlow
python -m venv .venv
.venv\Scripts\activate
pip install -r backend/requirements.txt
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend

```bash
cd DevFlow/frontend
npm install
npm run dev
```

## Docker

```bash
docker-compose up --build
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
