# Architecture

## Overview

DevFlow is organized around a distributed workflow execution pipeline:

1. The React frontend creates workflows and monitors runtime activity.
2. FastAPI exposes workflow, execution, monitoring, and websocket endpoints.
3. Workflow executions create durable queue records in the database.
4. Dedicated worker processes lease runnable jobs, execute task logic, and acknowledge completion.
5. Execution state, logs, queue records, and worker heartbeats are stored in the database.
6. The API broadcasts execution updates to connected clients.

## Backend Structure

- `backend/main.py`: application bootstrap, health probes, route registration, runtime startup.
- `backend/worker_main.py`: dedicated worker entrypoint for deployed worker containers or processes.
- `backend/api/routes`: HTTP and websocket routes.
- `backend/controllers`: thin HTTP orchestration layer.
- `backend/services`: workflow validation, execution orchestration, queue notifier, migrations, logging, seeding.
- `backend/queue`: durable queue abstraction backed by the database.
- `backend/workers`: worker runtime, lease renewal, heartbeat persistence.
- `backend/models`: SQLAlchemy entities for workflows, executions, queue jobs, worker records, and logs.

## Durable Queue Model

Queue jobs move through these states:

- `queued`: ready now or delayed until `available_at`.
- `leased`: claimed by a worker and protected by a renewable lease.
- `completed`: acknowledged after successful processing or terminal failure handling.

Workers renew job leases while they are active. If a worker crashes or disappears and its lease expires, the job is returned to `queued` automatically.

## Realtime Model

The frontend receives websocket notifications from the API process. Since workers may run separately, DevFlow uses a lightweight execution notifier that polls execution update timestamps from the database and rebroadcasts them through the API websocket layer.

## Deployment Topology

Recommended production topology:

- `frontend`: static assets served by Nginx.
- `api`: FastAPI app process.
- `worker`: one or more dedicated worker processes.
- `postgres`: shared relational database for workflows, executions, logs, queue jobs, and worker records.
