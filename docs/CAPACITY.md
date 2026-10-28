# Capacity Notes

Reference measurements for DevFlow on a single machine. These numbers are **evidence for regression and sizing intuition**, not a promise for every deployment: network latency, database tier, worker count, task duration, log volume, and webhook fan-out all change the result.

## Reference environment

| Component | Value |
| --- | --- |
| CPU | 8 logical cores |
| OS | Windows 11 (10.0.22631) |
| Python | 3.14.4 |
| Database | PostgreSQL 17.6, local loopback, default settings |
| API | 1 uvicorn process |
| Workers | 4 coroutines in the API process (`DEVFLOW_WORKER_COUNT=4`) |
| Test workflow | 2 sequential `sleep` tasks × 100 ms |
| Rate limits | Disabled for the probe (high per-key budget) |
| Tenant execution limit | Raised to 10,000 for the probe |
| Client | Node.js 22 HTTP keep-alive probe on the same host |

Reproduce with:

```bash
# Read probe: 5 s warm-up recommended, then 10 s at fixed concurrency
python scripts/load_test.py --base-url http://127.0.0.1:8000 --mode read --concurrency 20 --duration 10

# Execution probe: submit N runs, then wait for the queue to drain
python scripts/load_test.py --base-url http://127.0.0.1:8000 --mode run --run-executions 100 --concurrency 10
```

The script prints JSON with request counts, error rate, p50/p95/p99 latency, submission throughput, drain time, and execution totals.

## Measured results (2026-10-29)

| Probe | Concurrency | Throughput | p50 | p95 | p99 | Errors |
| --- | --- | --- | --- | --- | --- | --- |
| `GET /health` | 50 | 404 req/s | 122 ms | 170 ms | 188 ms | 0 |
| `GET /health` | 10 | 337 req/s | 27 ms | 46 ms | 67 ms | 0 |
| `GET /api/v1/workflows?limit=20` | 5 | 73 req/s | 58 ms | 143 ms | 199 ms | 0 |
| `GET /api/v1/workflows?limit=20` | 20 | 111 req/s | 146 ms | 299 ms | 602 ms | 0 |
| `POST /api/v1/workflows/{id}/run` + drain, 100 runs | 10 | 6.2 runs/s end-to-end | 322 ms | 633 ms | 701 ms | 0 |
| `POST /api/v1/workflows/{id}/run` + drain, 300 runs | 50 | 4.5 runs/s end-to-end | 2.2 s | 6.4 s | 7.8 s | 0 |

All 300 runs and 600 queue jobs completed with zero errors; `queued_jobs` and `in_flight_jobs` returned to zero. Server-side middleware durations for `/health` were ~1 ms; client-side percentiles include connection scheduling and queueing.

## How to read the numbers

- **Read throughput plateaus** around 100–110 req/s for authenticated workflow lists in this single-process setup. The list query performs authorization, tenant scoping, filtering, count, and serialization; horizontal API replicas are the first scaling lever.
- **Execution throughput is worker-bound.** Four workers with 100 ms tasks and per-job database state transitions sustain roughly 10–20 task jobs/s in this environment. Scale `worker` replicas (Kubernetes HPA/KEDA on queue lag) before increasing API replicas for job throughput.
- **Latency rises with concurrency** because the probe queues work at the client and the server has one event loop. p50 at 20–50 concurrent requests is not representative of a multi-replica deployment behind a load balancer.
- **SQLite is development-only.** Under concurrent writers it serialized and returned `database is locked` until the busy timeout was raised; the fix (30 s busy timeout) removes errors but not the throughput ceiling. PostgreSQL is required for production.
- **No autoscaling evidence yet.** HPA/KEDA manifests are provided, but the target cluster was not exercised in this environment. Capacity planning should be repeated against the real database tier and worker replica count.

## Sizing guidance

1. Start with 1 API replica per ~100 authenticated read req/s measured in *your* environment, then verify with a distributed load generator.
2. Size workers from queue lag: `tasks_per_second ≈ workers × (1 / average_task_seconds)`. Leave 30% headroom for retries and bursts.
3. Keep database pool size at or below `(max API replicas × pool_size) + (max worker replicas × pool_size)` that the database can serve. Defaults are 10 + 10 overflow per process.
4. Set `DEVFLOW_QUEUE_LEASE_SECONDS` comfortably above the expected task duration and heartbeat cadence (default 30 s lease, 5 s heartbeat).
5. Watch `devflow_queue_depth`, `devflow_task_wait_seconds`, and `devflow_task_duration_seconds` together; queue depth alone hides slow workers.
6. Run the execution probe before and after schema or worker changes to catch regressions. Store the JSON output with the release evidence.

## Known limits of this measurement

- Single host, loopback network, no TLS termination or ingress.
- Inline workers share the API event loop; dedicated worker processes should improve API latency under load.
- Webhooks, websocket fan-out, and retention jobs were idle during the probe.
- The probe uses a synthetic 100 ms sleep handler; real HTTP/SQL handlers add external latency and failure modes.
