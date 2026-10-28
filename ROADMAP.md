# DevFlow Production Readiness Roadmap

Living checklist for evolving DevFlow from a working workflow engine into a production-grade service. Keep this as the single source of truth: update statuses here instead of creating separate planning docs.

**Status legend:** `[x]` done and verified · `[~]` in progress · `[ ]` not started · `[!]` blocked

**Rules**
- IDs are stable. Never renumber; add new IDs at the end of a section.
- An item is `[x]` only when its *Done when* condition is met and evidence exists (test, command, or live check).
- Every new bug gets a `FIX-` ID, a regression test, and a status update here.
- Priorities: **P0** blocks production · **P1** required for a real launch · **P2** important · **P3** nice to have.

---

## Current verified baseline (2026-10-29)

| Check | Command | Result |
| --- | --- | --- |
| Backend lint | `ruff check backend` | pass |
| Backend tests | `python -m pytest` | 15 passed |
| Frontend build | `npm run build` | pass (158 kB JS) |
| API boot + seed | `uvicorn backend.main:app` | healthy, 2 workflows seeded |
| Golden path | Run "ML Training Pipeline" in UI | 4/4 tasks success, 4 workers idle, WS accepted |
| Runtime panel | Worker Monitor | readiness `ok`, DB `ok`, workers `running`, queue durable |
| Docker Compose | `docker compose up --build` | **not verified** (Docker daemon unavailable in the verification environment) |

Supported runtime: Python **3.12 / 3.13 / 3.14**, Node.js **20+**, PostgreSQL 16, SQLite for local development.

---

## 0. Defects fixed in this pass

- [x] **FIX-01 (P0)** — Frontend called `/api/health` and `/api/health/ready`, which return 404; header and readiness were permanently "unknown". Health calls now target the API root. *Verified by:* live UI shows `Ok` / `development` / `v1.0.0`; no 404s in console.
- [x] **FIX-02 (P0)** — A failed health call aborted `loadRuntime`, blanking queue and worker stats. Runtime load now uses `Promise.allSettled` and degrades per-source. *Verified by:* Worker Monitor shows 4 workers and processed counts.
- [x] **FIX-03 (P1)** — WebSocket never reconnected after a drop. Added exponential-backoff reconnect while an execution is selected.
- [x] **FIX-04 (P1)** — Workflow builder could not remove tasks, and task rows remounted on every keystroke (focus loss) because the React key included the editable name. Stable per-task IDs plus a Remove button added. *Verified by:* DOM shows "Remove task" (disabled for the single row).
- [x] **FIX-05 (P1)** — Every execution poll eagerly loaded all logs. Removed the unused eager load.
- [x] **FIX-06 (P1)** — Task/log reads loaded the full execution graph for an existence check. Added a scalar existence query.
- [x] **FIX-07 (P1)** — The execution notifier task died permanently on any DB error. Poll loop now logs and continues.
- [x] **FIX-08 (P1)** — A transient dequeue or heartbeat-write error killed a worker coroutine silently. Poll, lease-renewal, and heartbeat paths now log and recover.
- [x] **FIX-09 (P2)** — Stale-lease requeue ran on every 250 ms poll per worker (≈16 writes/sec). Requeue is now throttled to `min(lease/2, 5s)`.
- [x] **FIX-10 (P2)** — Queue stats swallowed database errors and reported healthy zeros. Errors are now logged.
- [x] **FIX-11 (P1)** — No upper bound on workflow size. API caps requests at 200 tasks and 100 dependencies per task.
- [x] **FIX-12 (P1)** — Logs endpoint was unbounded. Added `limit` (1–5000, default 1000) and `offset`.
- [x] **FIX-13 (P1)** — No request body limit. Added `DEVFLOW_MAX_REQUEST_BODY_BYTES` (default 1 MiB) returning `413`.
- [x] **FIX-14 (P1)** — No HTTP security headers. Added `X-Request-ID`, `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Cache-Control: no-store`, and production HSTS.
- [x] **FIX-15 (P1)** — Readiness reported `ok` with zero workers. Production readiness is now `degraded` unless workers are running.
- [x] **FIX-16 (P2)** — WebSocket accepted subscriptions for non-existent executions. It now rejects them with close code `1008`.
- [x] **FIX-17 (P2)** — Production could start with an empty CORS allowlist. Configuration validation now rejects it.
- [x] **FIX-18 (P2)** — SQLite local development had no WAL mode, busy timeout, or foreign-key enforcement, causing lock errors under concurrent workers. Added connection pragmas.
- [x] **FIX-19 (P2)** — The async engine was not disposed on shutdown. Lifespan now disposes it.
- [x] **FIX-20 (P1)** — `greenlet` (required by SQLAlchemy async) was missing from requirements. Added explicitly.
- [x] **FIX-21 (P1)** — Pinned dependencies could not install on Python 3.14 (no wheels) and were stale. Updated to current releases; verified install on 3.14 and CI matrix covers 3.12–3.14.
- [x] **FIX-22 (P2)** — README links used absolute Windows paths and were broken on GitHub. Converted to repository-relative links.
- [x] **FIX-23 (P1)** — API/worker containers ran as root. Added a dedicated non-root `app` user.
- [x] **FIX-24 (P2)** — Nginx served no security headers, compression, or cache policy. Added headers, gzip, immutable asset caching, and no-cache for `index.html`.
- [x] **FIX-25 (P1)** — Postgres password was hardcoded in Compose. It is now `${POSTGRES_PASSWORD}` with a local default; containers also get `no-new-privileges`, log rotation, init process, and grace periods.
- [x] **FIX-26 (P1)** — CI had no linting and only one Python version. Added `ruff` and a 3.12/3.13/3.14 matrix with read-only permissions and concurrency cancellation.
- [x] **FIX-27 (P1)** — No regression coverage for execution flow, retries, limits, headers, or body caps. Added integration and API tests (15 total).
- [x] **FIX-28 (P3)** — Pytest-asyncio emitted an unconfigured loop-scope warning. Configured explicitly.
- [x] **FIX-29 (P2)** — Frontend `fetch` calls could hang indefinitely. Added a 15 s abort timeout.
- [x] **FIX-30 (P2)** — Unhandled exceptions returned framework defaults without a safe JSON body or request correlation. Added a JSON 500 handler and `X-Request-ID`.

---

## 1. Security

- [ ] **SEC-01 (P0)** — Add authentication (OIDC or signed API keys) to every HTTP and WebSocket route. *Done when:* unauthenticated calls return 401 and tests cover it.
- [ ] **SEC-02 (P0)** — Add authorization/RBAC (viewer, operator, admin) and per-workflow ownership checks. *Done when:* cross-tenant reads/writes are denied and tested.
- [ ] **SEC-03 (P0)** — Add tenant isolation (`tenant_id` on all entities, scoped queries, scoped queue stats). *Done when:* two tenants cannot see each other's workflows, executions, logs, or workers.
- [ ] **SEC-04 (P1)** — Add rate limiting and per-tenant quotas (Redis-backed for multi-replica). *Done when:* burst tests return 429 and limits are configurable.
- [ ] **SEC-05 (P1)** — Serve the API over TLS with HSTS at an ingress/reverse proxy. *Done when:* HTTP redirects to HTTPS and TLS config is documented.
- [ ] **SEC-06 (P1)** — Move database credentials and signing keys to a secrets manager; remove defaults from deployment config. *Done when:* no secrets exist in Compose/env files used for production.
- [ ] **SEC-07 (P2)** — Validate and sandbox task configuration; never execute untrusted config as code. *Done when:* task handlers receive only allowlisted fields.
- [ ] **SEC-08 (P2)** — Add WAF/security-group rules and network policies between API, worker, and database. *Done when:* database is unreachable from outside the private network.
- [ ] **SEC-09 (P2)** — Add dependency and container vulnerability scanning to CI with a documented SLA. *Done when:* scans run on every PR and block high/critical findings.
- [ ] **SEC-10 (P2)** — Authenticate WebSocket connections and authorize per execution. *Done when:* an unauthorized socket cannot subscribe and is closed with 1008.
- [ ] **SEC-11 (P3)** — Add audit logging for privileged actions (workflow create/run/cancel, config changes). *Done when:* audit events are append-only and queryable.

## 2. Reliability & data integrity

- [ ] **REL-01 (P0)** — Replace ad-hoc `MigrationService` with Alembic migrations run as a one-off release job. *Done when:* schema changes are versioned and no service calls `create_all` in production.
- [ ] **REL-02 (P0)** — Add bounded retries for jobs orphaned by worker crashes. *Done when:* a task that repeatedly kills workers reaches a terminal failed state instead of retrying forever.
- [ ] **REL-03 (P1)** — Add a dead-letter state for terminal queue failures with operator visibility. *Done when:* failed jobs are queryable and replayable.
- [ ] **REL-04 (P1)** — Add a watchdog that marks executions/tasks orphaned by dead workers and finalizes them. *Done when:* a killed worker never leaves an execution `running` indefinitely.
- [ ] **REL-05 (P1)** — Implement graceful worker drain: stop claiming, finish in-flight tasks within the grace period, then exit. *Done when:* deploys do not requeue active tasks.
- [ ] **REL-06 (P1)** — Add idempotency keys for `POST /workflows/{id}/run` to prevent duplicate executions on retries. *Done when:* repeating a request with the same key returns the original execution.
- [ ] **REL-07 (P1)** — Add retention and cleanup jobs for logs, completed queue records, and stale worker records. *Done when:* retention is configurable and covered by tests.
- [ ] **REL-08 (P1)** — Set database connection pool sizing/timeouts and document capacity per replica. *Done when:* load tests show stable pool usage at target concurrency.
- [ ] **REL-09 (P2)** — Add transactional outbox or equivalent so execution state and broadcasts cannot diverge. *Done when:* no lost-update window between commit and notification remains.
- [ ] **REL-10 (P2)** — Add automated Postgres backups with point-in-time recovery and a restore drill. *Done when:* a documented restore meets the RPO/RTO targets.
- [ ] **REL-11 (P2)** — Add task-level timeout/watchdog independent of the queue lease. *Done when:* hung tasks fail deterministically.
- [ ] **REL-12 (P3)** — Add graceful API shutdown draining active requests before exit. *Done when:* rolling deploys produce zero client 5xx spikes.

## 3. Queue & worker runtime

- [ ] **QUE-01 (P0)** — Use `SELECT ... FOR UPDATE SKIP LOCKED` (or equivalent) for claims on Postgres. *Done when:* contention tests with many workers show no duplicate execution.
- [ ] **QUE-02 (P1)** — Give worker instances unique IDs (hostname/replica suffix) so scaling does not collide on `worker-1..N`. *Done when:* two worker replicas both appear in monitoring.
- [ ] **QUE-03 (P1)** — Add per-workflow and global concurrency limits. *Done when:* limits are enforced and surfaced in the API.
- [ ] **QUE-04 (P1)** — Add fair scheduling or priority aging so low-priority work cannot starve. *Done when:* a long low-priority backlog still drains.
- [ ] **QUE-05 (P1)** — Add a real task-handler registry (pluggable callables by task type) instead of simulated sleeps. *Done when:* at least one real handler type runs through the same lifecycle.
- [ ] **QUE-06 (P2)** — Add queue backend abstraction with a Redis/SQS implementation behind the existing interface. *Done when:* queue tests run against two backends.
- [ ] **QUE-07 (P2)** — Add poison-job detection (same job repeatedly requeued) with quarantine. *Done when:* a poison job is quarantined and alerted.
- [ ] **QUE-08 (P2)** — Add delayed/scheduled jobs and cron-style triggers. *Done when:* a recurring workflow can be configured and observed.
- [ ] **QUE-09 (P2)** — Emit task duration, wait time, and retry metrics per worker. *Done when:* metrics back a dashboard.
- [ ] **QUE-10 (P3)** — Add queue sharding/partitioning plan for growth beyond a single Postgres queue table. *Done when:* capacity model and migration path are documented.

## 4. API & contracts

- [ ] **API-01 (P0)** — Add `GET /api/executions` with pagination, status filter, and workflow filter. *Done when:* the UI can list history without knowing IDs.
- [ ] **API-02 (P0)** — Add `POST /api/executions/{id}/cancel` and `POST /api/executions/{id}/retry`. *Done when:* cancellation stops pending work and is audited.
- [ ] **API-03 (P1)** — Paginate `GET /api/workflows` and document all list contracts. *Done when:* large tenants do not receive unbounded payloads.
- [ ] **API-04 (P1)** — Add `PATCH`/`DELETE` for workflows with versioning or immutable revisions. *Done when:* edits do not mutate in-flight executions.
- [ ] **API-05 (P1)** — Version the API (`/api/v1`) and publish a deprecation policy. *Done when:* breaking changes can ship without client breakage.
- [ ] **API-06 (P1)** — Standardize error payloads (`code`, `message`, `request_id`, `details`) across 4xx/5xx. *Done when:* clients parse one error shape.
- [ ] **API-07 (P2)** — Generate typed clients from OpenAPI and add contract tests. *Done when:* CI fails on an accidental breaking schema change.
- [ ] **API-08 (P2)** — Add cursor pagination for logs (offset becomes expensive at scale). *Done when:* log paging is stable under concurrent inserts.
- [ ] **API-09 (P2)** — Return queue/database health explicitly instead of zeroed stats when queries fail. *Done when:* readiness and queue endpoints expose degradation.
- [ ] **API-10 (P3)** — Add bulk workflow import/export (JSON/YAML). *Done when:* round-trip import preserves DAG and config.

## 5. Frontend & UX

- [ ] **UI-01 (P1)** — Add a top-level React error boundary with a recoverable fallback. *Done when:* a render error does not blank the app.
- [ ] **UI-02 (P1)** — Add client-side validation and inline errors for the workflow builder (duplicates, unknown dependencies, numeric bounds). *Done when:* mistakes are caught before submit.
- [ ] **UI-03 (P1)** — Add execution history list, filters, and links from the dashboard. *Done when:* users can inspect past runs without an ID.
- [ ] **UI-04 (P1)** — Add loading, empty, and error states for every panel. *Done when:* slow/failed APIs never look like empty data.
- [ ] **UI-05 (P1)** — Audit responsive layouts at 360, 390, 768, 1024, and 1440 px with screenshots. *Done when:* no horizontal scroll or clipped controls.
- [ ] **UI-06 (P2)** — Add URL routing (deep links to executions/pages) instead of local tab state. *Done when:* refreshing or sharing a URL restores the view.
- [ ] **UI-07 (P2)** — Visualize DAG edges, not just task cards. *Done when:* dependencies are traceable in the graph view.
- [ ] **UI-08 (P2)** — Add accessibility pass (labels, focus states, contrast, keyboard navigation) with axe checks. *Done when:* automated a11y checks pass with no critical issues.
- [ ] **UI-09 (P2)** — Add frontend unit/component tests (Vitest + Testing Library). *Done when:* core pages and API error paths are covered.
- [ ] **UI-10 (P3)** — Add confirmation dialogs for destructive/expensive actions (run, cancel, delete). *Done when:* no accidental destructive action is one click away.
- [ ] **UI-11 (P3)** — Add i18n scaffolding if multi-language is a requirement. *Done when:* strings are externalized and a second locale renders.

## 6. Observability

- [ ] **OBS-01 (P0)** — Emit structured JSON logs with request/execution/task/worker IDs. *Done when:* logs can be filtered by correlation ID.
- [ ] **OBS-02 (P0)** — Expose Prometheus metrics (`/metrics`) for requests, queue depth, job latency, retries, worker states. *Done when:* a dashboard shows all golden signals.
- [ ] **OBS-03 (P1)** — Propagate `X-Request-ID` into logs and responses end to end. *Done when:* one ID traces API → queue → worker.
- [ ] **OBS-04 (P1)** — Add OpenTelemetry tracing across API, queue, and worker. *Done when:* a single execution produces one trace.
- [ ] **OBS-05 (P1)** — Define SLOs and alerts (API latency/error rate, queue lag, execution failure rate, worker heartbeat loss). *Done when:* alerts page on SLO burn.
- [ ] **OBS-06 (P1)** — Add health/readiness dashboards and runbook links in alert annotations. *Done when:* each alert links to an actionable runbook.
- [ ] **OBS-07 (P2)** — Add log retention/search and PII scrubbing. *Done when:* logs contain no secrets/PII and retention is enforced.
- [ ] **OBS-08 (P2)** — Add worker/queue diagnostics endpoint for support (last errors, lease state). *Done when:* support can diagnose without DB access.

## 7. Testing & QA

- [ ] **TEST-01 (P0)** — Add end-to-end browser tests (Playwright) for create → run → dashboard → logs. *Done when:* CI runs the golden path against the built stack.
- [ ] **TEST-02 (P1)** — Add Postgres-backed integration tests (not only SQLite). *Done when:* CI runs the suite against Postgres 16.
- [ ] **TEST-03 (P1)** — Add concurrency tests: multiple workers claiming, lease expiry, duplicate prevention. *Done when:* claim races are proven safe.
- [ ] **TEST-04 (P1)** — Enforce coverage thresholds (backend and frontend). *Done when:* CI fails below the agreed threshold.
- [ ] **TEST-05 (P2)** — Add load tests (k6/Locust) for API and worker throughput. *Done when:* capacity numbers are documented from evidence.
- [ ] **TEST-06 (P2)** — Add chaos tests (kill worker/API/DB mid-execution) and recovery assertions. *Done when:* documented recovery paths pass.
- [ ] **TEST-07 (P2)** — Add tests for WebSocket auth/reconnect and notifier failure recovery. *Done when:* these paths are covered.
- [ ] **TEST-08 (P3)** — Add mutation testing for critical DAG/queue logic. *Done when:* mutation score meets the target.

## 8. CI/CD & supply chain

- [ ] **CI-01 (P0)** — Build Docker images in CI (api/worker/frontend) on every PR. *Done when:* image builds are gated.
- [ ] **CI-02 (P1)** — Add lockfiles with hashes (`pip-compile --generate-hashes` or uv) and automated dependency updates (Dependabot/Renovate). *Done when:* installs are reproducible and update PRs are automated.
- [ ] **CI-03 (P1)** — Add SBOM generation and image signing (e.g., cosign). *Done when:* releases ship verifiable artifacts.
- [ ] **CI-04 (P1)** — Add a staging deploy pipeline with smoke tests before production. *Done when:* production promotion requires a green staging run.
- [ ] **CI-05 (P2)** — Add database migration check to the deploy pipeline. *Done when:* incompatible migrations fail before rollout.
- [ ] **CI-06 (P2)** — Add branch protection, required reviews, CODEOWNERS, and PR template. *Done when:* main cannot be pushed without review/CI.
- [ ] **CI-07 (P2)** — Add release versioning and changelog automation. *Done when:* every release is tagged with generated notes.

## 9. Infrastructure & deployment

- [ ] **INF-01 (P0)** — Verify `docker compose up --build` end to end (currently unverified). *Done when:* all four services are healthy and the golden path passes in containers.
- [ ] **INF-02 (P0)** — Add a production deployment target (Kubernetes/ECS) with Ingress/TLS, HPA, PDB, resource requests/limits, and network policies. *Done when:* a production-like environment runs the stack.
- [ ] **INF-03 (P1)** — Add worker container health/readiness (heartbeat or admin port). *Done when:* orchestrators can detect a dead worker.
- [ ] **INF-04 (P1)** — Add Compose/K8s resource limits and log rotation for all services. *Done when:* no container can exhaust the host.
- [ ] **INF-05 (P1)** — Make the Postgres volume durable, backed up, and monitored. *Done when:* disk growth and backup success are alerted.
- [ ] **INF-06 (P2)** — Add a reverse proxy/ingress serving the UI and API under one origin. *Done when:* CORS is unnecessary in production.
- [ ] **INF-07 (P2)** — Document disaster recovery (RPO/RTO, restore steps, ownership). *Done when:* a restore drill has been executed.
- [ ] **INF-08 (P2)** — Add environment separation (dev/staging/prod) with isolated databases and secrets. *Done when:* no shared state across environments.
- [ ] **INF-09 (P3)** — Add cost/usage guardrails and autoscaling policies for workers. *Done when:* scale-out follows queue lag.

## 10. Docs & governance

- [ ] **DOC-01 (P1)** — Add `LICENSE` and finalize ownership/attribution terms. *Done when:* the repository has an explicit license.
- [ ] **DOC-02 (P1)** — Add `SECURITY.md` (vulnerability reporting, supported versions). *Done when:* the process is published.
- [ ] **DOC-03 (P1)** — Add architecture decision records (ADRs) for queue, realtime, and storage choices. *Done when:* major decisions have dated records.
- [ ] **DOC-04 (P1)** — Document SLOs, on-call expectations, and escalation. *Done when:* the runbook covers detection → mitigation.
- [ ] **DOC-05 (P2)** — Keep [docs/API.md](docs/API.md) generated/validated against OpenAPI. *Done when:* docs drift fails CI.
- [ ] **DOC-06 (P2)** — Add a production deployment checklist distinct from this roadmap. *Done when:* releases follow a repeatable gate list.
- [ ] **DOC-07 (P3)** — Add screenshots/GIFs and a demo script to the README. *Done when:* a new user can evaluate the project in one minute.

## 11. Product features

- [ ] **FEAT-01 (P1)** — Workflow editing, cloning, and deletion with immutable execution snapshots. *Done when:* edits never mutate running executions.
- [ ] **FEAT-02 (P1)** — Execution history, search, and comparison. *Done when:* users can diff two runs.
- [ ] **FEAT-03 (P1)** — Manual task retry and skip from the UI. *Done when:* operators can recover a single failed branch.
- [ ] **FEAT-04 (P2)** — Real task types (HTTP, SQL, shell, container) with typed config. *Done when:* each type has validation and tests.
- [ ] **FEAT-05 (P2)** — Secrets references in task config (never stored in plaintext). *Done when:* configs reference secret IDs only.
- [ ] **FEAT-06 (P2)** — Notifications/webhooks on execution success/failure. *Done when:* delivery is retried and observable.
- [ ] **FEAT-07 (P2)** — Workflow templates and a sample gallery. *Done when:* new users can start from a template.
- [ ] **FEAT-08 (P3)** — Multi-step approval gates and manual checkpoints. *Done when:* an execution can pause for approval.

## 12. Scale & architecture

- [ ] **SCALE-01 (P1)** — Document capacity targets (workflows/day, concurrent tasks, queue depth) and validate with load tests. *Done when:* targets are measured, not estimated.
- [ ] **SCALE-02 (P2)** — Move WebSocket fan-out to a shared bus (Redis pub/sub or Postgres LISTEN/NOTIFY) for multiple API replicas. *Done when:* clients connected to different replicas receive the same events.
- [ ] **SCALE-03 (P2)** — Partition/archive queue and log tables as volume grows. *Done when:* query latency stays within SLO after archival.
- [ ] **SCALE-04 (P2)** — Add read replicas or caching for dashboard queries. *Done when:* read load does not contend with worker writes.
- [ ] **SCALE-05 (P3)** — Evaluate a dedicated broker (Redis Streams, SQS, Kafka) if Postgres queue throughput becomes the bottleneck. *Done when:* a benchmark-backed decision is recorded.
- [ ] **SCALE-06 (P3)** — Multi-region/DR topology design. *Done when:* failover is tested and documented.

---

## Definition of done for "production-grade"

All P0 items are `[x]`, and:

1. Every request and socket is authenticated, authorized, and tenant-scoped.
2. Schema changes ship through versioned migrations; no runtime `create_all`.
3. Crashed workers, poison jobs, and hung tasks reach a terminal, visible state.
4. Metrics, structured logs, traces, SLOs, and alerts exist for API and workers.
5. CI builds images, runs backend + Postgres + E2E tests, lints, scans, and signs artifacts.
6. A production deployment target runs with TLS, resource limits, backups, and a tested restore.
7. Security, licensing, ADRs, and on-call documentation are published.

## Suggested execution order

1. **Blockers:** SEC-01/02/03, REL-01/02, API-01/02, QUE-01, OBS-01/02, TEST-01, CI-01, INF-01/02.
2. **Launch hardening:** SEC-04/05/06, REL-03/04/05/06/07, QUE-02/03/05, API-03/05/06, UI-01–05, OBS-03/04/05, CI-02/03/04, INF-03/04/05.
3. **Scale and polish:** everything else, driven by measured bottlenecks.

When an item completes, update its checkbox and add the verification evidence to the baseline table.
