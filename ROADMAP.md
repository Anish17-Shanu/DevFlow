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
| Backend lint | `ruff check backend migrations` / `ruff format --check …` | pass |
| Backend tests (SQLite) | `python -m pytest` | **78 passed, 2 skipped** (Postgres-only tests skipped) |
| Backend tests + PostgreSQL | `DEVFLOW_TEST_POSTGRES_URL=… python -m pytest --cov=backend` | **80 passed, 79.04% coverage** (threshold 70%) |
| Frontend unit tests | `npm run test:coverage` | **35 passed** across 5 files; thresholds enforced |
| Frontend build | `npm run build` | pass |
| Browser E2E | `npm run test:e2e` | **2 passed**: golden path + 5 responsive widths (360–1440) |
| Docker Compose | `docker compose up -d --build` | **all 5 services healthy**, migration exited 0, smoke test passed, UI run succeeded in `production` |
| Kubernetes manifests | `kubectl kustomize deploy/k8s` | valid |
| API docs drift | `python scripts/generate_api_docs.py --check` | matches OpenAPI |
| Cross-replica WebSocket | 2 API replicas + 1 worker on PostgreSQL | both clients received the identical event exactly once |
| Process kill / drain | `pytest backend/tests/test_services.py` | in-flight task completes during shutdown |

Supported runtime: Python **3.12 / 3.13 / 3.14**, Node.js **20+**, PostgreSQL 16–17, SQLite for local development.

**Environment caveats:** Kubernetes was validated with `kustomize` only (no live cluster). The staging/production deploy workflow is committed but has not run on GitHub Actions infrastructure from this workstation. Branch protection is a repository setting and is not verifiable from the codebase.

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

- [x] **SEC-01 (P0)** — Hashed API keys on every HTTP/WebSocket route; bootstrap key in development. *Evidence:* `backend/api/dependencies.py`, `backend/tests/test_auth_api.py` (401/403 cases).
- [x] **SEC-02 (P0)** — RBAC viewer/operator/admin plus tenant-scoped repository queries. *Evidence:* cross-tenant 404s in `test_workflows_api.py`, `test_executions_api.py`, `test_realtime.py`.
- [x] **SEC-03 (P0)** — `tenant_id` on all entities; scoped workflow, execution, log, queue, worker and audit queries. *Evidence:* two-tenant API tests and admin auth-key isolation.
- [x] **SEC-04 (P1)** — Token-bucket rate limiting with in-memory and Redis backends, configurable per key. *Evidence:* `backend/core/rate_limit.py`, 429 test with `Retry-After`.
- [x] **SEC-05 (P1)** — TLS with forced redirect and cert-manager annotations in `deploy/k8s/ingress.yaml`; HSTS emitted in production. *Evidence:* ingress manifest + `Strict-Transport-Security` in `backend/main.py`.
- [x] **SEC-06 (P1)** — No production secrets in the repo: Compose requires env, K8s uses a Secret, production settings reject defaults. *Evidence:* `docker-compose.yml` required vars, `secret.example.yaml`, config validator.
- [x] **SEC-07 (P2)** — Handlers validate typed config fields; no arbitrary code execution path. *Evidence:* `backend/handlers/builtin.py`, config validation tests.
- [x] **SEC-08 (P2)** — Default-deny NetworkPolicy limits API/worker/Postgres ingress. *Evidence:* `deploy/k8s/networkpolicy.yaml`.
- [x] **SEC-09 (P2)** — Trivy scans block HIGH/CRITICAL findings; SBOM generated per CI run. *Evidence:* `docker` job in `.github/workflows/ci.yml`.
- [x] **SEC-10 (P2)** — WebSocket authentication plus per-execution tenant authorization, close code 1008. *Evidence:* `backend/tests/test_realtime.py` (5 socket tests).
- [x] **SEC-11 (P3)** — Append-only audit events for privileged actions, exposed via `GET /api/v1/audit`. *Evidence:* `backend/services/audit_service.py`, `ops_routes.py`, `test_ops_api.py`.

## 2. Reliability & data integrity

- [x] **REL-01 (P0)** — Alembic migrations with a one-off release job; production rejects `auto_migrate`. *Evidence:* `migrations/`, Compose `migrate` service exited 0, `validate_production_settings`.
- [x] **REL-02 (P0)** — Bounded retries via poison-attempt accounting; repeated crashes reach terminal failure. *Evidence:* `queue_poison_max_attempts`, `test_database_queue.py`.
- [x] **REL-03 (P1)** — Dead-letter state with listing and replay endpoints. *Evidence:* `test_ops_api.py`, `test_database_queue.py`.
- [x] **REL-04 (P1)** — Watchdog reclaims expired leases and finalizes orphaned executions/tasks. *Evidence:* `watchdog_service.py`, `test_services.py`.
- [x] **REL-05 (P1)** — Graceful worker drain: stop claiming, finish in-flight work, then exit. *Evidence:* `test_worker_shutdown_drains_inflight_task`.
- [x] **REL-06 (P1)** — Idempotency keys on workflow runs return the original execution. *Evidence:* `test_executions_api.py`.
- [x] **REL-07 (P1)** — Configurable retention for logs, executions, queue and worker rows. *Evidence:* `test_retention.py`.
- [x] **REL-08 (P1)** — Pool sizing/timeouts documented and load-tested. *Evidence:* [docs/CAPACITY.md](docs/CAPACITY.md), `test_postgres_integration.py`.
- [x] **REL-09 (P2)** — Transactional outbox drives execution notifications, so state and broadcast cannot diverge. *Evidence:* `outbox_service.py`, `outbox_notifier_service.py`, notifier recovery test.
- [~] **REL-10 (P2)** — Logical backup/restore scripts and drill procedure exist; continuous WAL archiving/PITR is documented as the RPO 15 min mechanism but must be enabled by the platform. *Evidence:* `scripts/backup_postgres.sh`, `scripts/restore_postgres.sh`, [docs/RUNBOOK.md](docs/RUNBOOK.md#backup-and-restore-drill).
- [x] **REL-11 (P2)** — Independent task timeout watchdog fails hung tasks deterministically. *Evidence:* `max_task_timeout_seconds`, `watchdog_service.py`.
- [~] **REL-12 (P3)** — Lifespan shutdown drains services and workers within the orchestrator grace period; zero-5xx rolling-deploy behavior is not measured yet.

## 3. Queue & worker runtime

- [x] **QUE-01 (P0)** — `SELECT … FOR UPDATE SKIP LOCKED` claims; four-worker contention test proves no duplicate execution. *Evidence:* `test_parallel_claims_never_duplicate_on_postgres`.
- [x] **QUE-02 (P1)** — Unique worker instance IDs (host/replica suffix). *Evidence:* `backend/workers/heartbeat.py`, `worker_main.py`, readiness test.
- [x] **QUE-03 (P1)** — Per-workflow and per-tenant concurrency limits with 429/queue backpressure. *Evidence:* `max_concurrent_tasks_per_workflow`, `max_concurrent_executions_per_tenant`, tests.
- [x] **QUE-04 (P1)** — Priority aging prevents low-priority starvation. *Evidence:* `queue_aging_seconds`, queue tests.
- [x] **QUE-05 (P1)** — Pluggable task-handler registry. *Evidence:* `backend/handlers/registry.py`, `builtin.py` (sleep/echo/http/fail).
- [ ] **QUE-06 (P2)** — Queue backend abstraction with Redis/SQS implementation. Only the durable database backend exists.
- [x] **QUE-07 (P2)** — Poison-job detection with quarantine and dead-letter visibility. *Evidence:* queue tests.
- [x] **QUE-08 (P2)** — Delayed jobs and cron-style scheduled workflows. *Evidence:* `scheduler_service.py`, `test_services.py`.
- [x] **QUE-09 (P2)** — Task wait/duration/retry metrics per worker. *Evidence:* `backend/core/metrics.py`, Grafana dashboard.
- [ ] **QUE-10 (P3)** — Queue sharding/partitioning plan. Not designed; single-table queue is within measured capacity.

## 4. API & contracts

- [x] **API-01 (P0)** — Paginated execution history with status/workflow filters. *Evidence:* `GET /api/v1/executions`, `test_executions_api.py`.
- [x] **API-02 (P0)** — Cancel and retry endpoints with audit events. *Evidence:* `execution_routes.py`, API tests.
- [x] **API-03 (P1)** — Paginated workflow listing with search/archive filters. *Evidence:* `test_workflows_api.py`.
- [x] **API-04 (P1)** — Workflow update/delete/clone with immutable execution snapshots and revision numbers. *Evidence:* `workflow_service.py`, `test_executions_api.py` (snapshot uses revision).
- [x] **API-05 (P1)** — Versioned `/api/v1` prefix. *Evidence:* `settings.api_prefix`, OpenAPI docs.
- [x] **API-06 (P1)** — One error envelope (`code`, `message`, `request_id`, `details`) on 4xx/5xx. *Evidence:* `backend/main.py` exception handlers, API tests.
- [ ] **API-07 (P2)** — Generated typed clients and contract tests. API.md drift check exists; generated clients do not.
- [ ] **API-08 (P2)** — Cursor pagination for logs. Offset pagination only.
- [x] **API-09 (P2)** — Queue/readiness expose `error` and `healthy: false` instead of zeros. *Evidence:* `QueueStats`, readiness response.
- [ ] **API-10 (P3)** — Bulk workflow import/export. Not implemented.

## 5. Frontend & UX

- [x] **UI-01 (P1)** — Top-level error boundary with recoverable fallback. *Evidence:* `ErrorBoundary.jsx`, component test.
- [x] **UI-02 (P1)** — Builder validation for duplicates, unknown dependencies, bounds. *Evidence:* `WorkflowBuilderPage.jsx`, pages tests.
- [x] **UI-03 (P1)** — Execution history with filters and workflow links. *Evidence:* `ExecutionsPage.jsx`, E2E golden path.
- [x] **UI-04 (P1)** — Loading, empty and error states on every panel. *Evidence:* `EmptyState.jsx`, page tests.
- [x] **UI-05 (P1)** — Responsive audit at 360/390/768/1024/1440 with committed screenshots. *Evidence:* `frontend/e2e/responsive.spec.js`, `docs/screenshots/`.
- [x] **UI-06 (P2)** — Hash routing with deep links to workflows, executions and panels. *Evidence:* `src/lib/router.js`, `App.jsx`.
- [x] **UI-07 (P2)** — DAG edges rendered, not just cards. *Evidence:* `TaskGraph.jsx`, component tests.
- [ ] **UI-08 (P2)** — Automated axe accessibility checks. Not wired into CI.
- [x] **UI-09 (P2)** — Vitest + Testing Library coverage of pages and API error paths. *Evidence:* 35 tests across 5 files.
- [x] **UI-10 (P3)** — Confirmation dialogs for run/archive/delete. *Evidence:* `ConfirmDialog.jsx`, verified in live UI ("Start a new run?").
- [ ] **UI-11 (P3)** — i18n scaffolding. Not implemented; single locale by design.

## 6. Observability

- [x] **OBS-01 (P0)** — Structured JSON logs with request/execution/task/worker correlation. *Evidence:* `backend/core/logging.py`, `context.py`.
- [x] **OBS-02 (P0)** — Prometheus metrics and Grafana dashboard for golden signals. *Evidence:* `/metrics`, `deploy/observability/`.
- [x] **OBS-03 (P1)** — `X-Request-ID` echoed, logged and bound into worker execution context. *Evidence:* middleware + execution service.
- [~] **OBS-04 (P1)** — Optional OTel FastAPI/HTTPX/SQLAlchemy instrumentation exists; worker spans are not yet linked into one execution trace.
- [x] **OBS-05 (P1)** — Seven SLO alerts on latency, errors, queue lag, failure rate and heartbeat loss. *Evidence:* `deploy/observability/alerts.yml`.
- [x] **OBS-06 (P1)** — Alert annotations link to actionable runbook sections. *Evidence:* `docs/RUNBOOK.md`.
- [~] **OBS-07 (P2)** — Log retention is enforced; no dedicated PII scrubbing/search stack (operator-provided).
- [x] **OBS-08 (P2)** — Operations endpoints expose worker state, dead letters and audit without DB access. *Evidence:* `ops_routes.py`, `test_ops_api.py`.

## 7. Testing & QA

- [x] **TEST-01 (P0)** — Playwright golden path in CI (create → run → dashboard → logs). *Evidence:* `frontend/e2e/golden-path.spec.js`, CI `e2e` job; 2/2 passing locally.
- [x] **TEST-02 (P1)** — PostgreSQL 16 integration job in CI and local run. *Evidence:* `test_postgres_integration.py`, CI `postgres` job, 80-test Postgres run.
- [x] **TEST-03 (P1)** — Concurrency, lease-expiry and duplicate-prevention tests. *Evidence:* queue and worker tests.
- [x] **TEST-04 (P1)** — Backend 70% and frontend coverage thresholds enforced. *Evidence:* `pytest.ini`, `vitest.config.js` (backend measured 79.04%).
- [x] **TEST-05 (P2)** — Load probes and measured capacity table. *Evidence:* `scripts/load_test.py`, [docs/CAPACITY.md](docs/CAPACITY.md).
- [~] **TEST-06 (P2)** — Recovery tests cover worker shutdown with in-flight work and notifier poll failures; killing Postgres/API mid-execution is not automated.
- [x] **TEST-07 (P2)** — WebSocket auth/reconnect and notifier failure recovery tests. *Evidence:* `test_realtime.py`, `pages.test.jsx`, `test_services.py`.
- [ ] **TEST-08 (P3)** — Mutation testing. Not configured.

## 8. CI/CD & supply chain

- [x] **CI-01 (P0)** — API and frontend images build and are scanned on every PR. *Evidence:* CI `docker` job runs after backend/frontend gates.
- [x] **CI-02 (P1)** — Hashed lockfiles installed with `--require-hashes`; Dependabot groups weekly pip/npm/actions/docker updates. *Evidence:* `backend/requirements*.lock`, `.github/dependabot.yml`.
- [x] **CI-03 (P1)** — SBOM artifact per build; release images signed with cosign keyless. *Evidence:* CI `docker` and `release` jobs, `deploy.yml`.
- [~] **CI-04 (P1)** — Staging→production deploy workflow with smoke test and environment gate is committed but has not executed on GitHub runners.
- [x] **CI-05 (P2)** — Deploy runs Alembic as a release job and waits for completion before rollout. *Evidence:* Compose `migrate`, `deploy.yml` migration job handling.
- [~] **CI-06 (P2)** — CODEOWNERS and PR template are present; branch protection/review requirements are repository settings and were not changed.
- [x] **CI-07 (P2)** — `v*` tags build/push images and create a GitHub release with generated notes. *Evidence:* CI `release` job.

## 9. Infrastructure & deployment

- [x] **INF-01 (P0)** — `docker compose up --build` verified end to end. *Evidence:* PostgreSQL, migrate (exit 0), API, worker and frontend all healthy; `scripts/smoke_test.sh` passed; golden path run succeeded through the containerized UI.
- [~] **INF-02 (P0)** — Kubernetes manifests (Ingress/TLS, HPA, PDB, resources, NetworkPolicy) render with `kustomize`; no live production-like cluster was available to run them.
- [x] **INF-03 (P1)** — Dedicated worker heartbeat health check; Compose reports the worker healthy. *Evidence:* `backend/worker_healthcheck.py`, `docker compose ps`.
- [x] **INF-04 (P1)** — Resource limits, init/grace periods and log rotation on every service. *Evidence:* `docker-compose.yml`, K8s manifests.
- [~] **INF-05 (P1)** — Durable Postgres volume plus backup/restore scripts; backup-success alerting depends on platform monitoring.
- [x] **INF-06 (P2)** — Nginx serves UI and proxies `/api`, `/ws`, `/health`, `/metrics` on one origin. *Evidence:* `frontend/nginx.conf`, verified at `http://127.0.0.1:18080`.
- [~] **INF-07 (P2)** — DR objectives, escalate/restore steps documented; no restore drill was executed in this pass.
- [~] **INF-08 (P2)** — Staging and production GitHub Environments with separate secrets are defined; K8s ships one overlay, so full environment isolation is deployment-owned.
- [~] **INF-09 (P3)** — Worker autoscaling guidance (KEDA queue-lag trigger) documented; not deployed.

## 10. Docs & governance

- [x] **DOC-01 (P1)** — MIT license and attribution. *Evidence:* `LICENSE`.
- [x] **DOC-02 (P1)** — Vulnerability reporting and supported versions. *Evidence:* `SECURITY.md`.
- [x] **DOC-03 (P1)** — Dated ADRs for queue, realtime and storage. *Evidence:* `docs/adr/`.
- [x] **DOC-04 (P1)** — SLOs, error-budget policy, escalation and runbook. *Evidence:* `docs/RUNBOOK.md`.
- [x] **DOC-05 (P2)** — API reference validated against OpenAPI in CI. *Evidence:* `scripts/generate_api_docs.py --check` passes.
- [x] **DOC-06 (P2)** — Release gate checklist separate from this roadmap. *Evidence:* `docs/PRODUCTION_CHECKLIST.md`.
- [x] **DOC-07 (P3)** — Screenshots, quickstart and API tour in the README. *Evidence:* `README.md`, `docs/screenshots/`.

## 11. Product features

- [x] **FEAT-01 (P1)** — Workflow edit/clone/archive with immutable execution snapshots. *Evidence:* workflow API and revision tests.
- [~] **FEAT-02 (P1)** — Execution history and filtering exist; side-by-side run comparison is not implemented.
- [x] **FEAT-03 (P1)** — Per-task retry and skip from the UI. *Evidence:* execution detail page, API tests.
- [~] **FEAT-04 (P2)** — Real HTTP/sleep/echo/fail handlers with typed config; SQL, shell and container handlers are intentionally not included.
- [x] **FEAT-05 (P2)** — `{{secret:name}}` references resolved from encrypted secret storage. *Evidence:* `secret_service.py`, handler tests.
- [x] **FEAT-06 (P2)** — HMAC-signed webhooks with retries and delivery records. *Evidence:* `webhook_service.py`, tests.
- [x] **FEAT-07 (P2)** — Template gallery creates editable workflows. *Evidence:* `backend/sample_data/templates.py`, verified in live UI.
- [ ] **FEAT-08 (P3)** — Approval gates/manual checkpoints. Not implemented.

## 12. Scale & architecture

- [x] **SCALE-01 (P1)** — Measured capacity table with methodology and caveats. *Evidence:* [docs/CAPACITY.md](docs/CAPACITY.md).
- [x] **SCALE-02 (P2)** — Shared Postgres `LISTEN/NOTIFY` bus for cross-replica WebSocket fan-out. *Evidence:* `test_realtime_bus_fans_out_across_replicas`; live two-replica run delivered the same event once to a client on each replica.
- [ ] **SCALE-03 (P2)** — Queue/log partitioning and archival. Not implemented.
- [ ] **SCALE-04 (P2)** — Read replicas or dashboard caching. Not implemented.
- [ ] **SCALE-05 (P3)** — Broker evaluation. Not started; Postgres queue is within measured capacity.
- [ ] **SCALE-06 (P3)** — Multi-region/DR topology. Not designed.

---

## Definition of done for "production-grade"

All P0 items are `[x]` except **INF-02**, which is `[~]`: manifests validate, but no live production-like cluster was available. The remaining condition is an operational environment check, not missing code.

1. Every request and socket is authenticated, authorized, and tenant-scoped.
2. Schema changes ship through versioned migrations; no runtime `create_all`.
3. Crashed workers, poison jobs, and hung tasks reach a terminal, visible state.
4. Metrics, structured logs, traces, SLOs, and alerts exist for API and workers.
5. CI builds images, runs backend + Postgres + E2E tests, lints, scans, and signs artifacts.

**Next candidates (all P2/P3, tracked above):** QUE-06, QUE-10, API-07/08/10, UI-08/11, TEST-08, FEAT-08, SCALE-03/04/05/06, plus live-cluster verification for INF-02 and a real restore drill for REL-10/INF-07.
6. A production deployment target runs with TLS, resource limits, backups, and a tested restore.
7. Security, licensing, ADRs, and on-call documentation are published.

## Suggested execution order

1. **Blockers:** SEC-01/02/03, REL-01/02, API-01/02, QUE-01, OBS-01/02, TEST-01, CI-01, INF-01/02.
2. **Launch hardening:** SEC-04/05/06, REL-03/04/05/06/07, QUE-02/03/05, API-03/05/06, UI-01–05, OBS-03/04/05, CI-02/03/04, INF-03/04/05.
3. **Scale and polish:** everything else, driven by measured bottlenecks.

When an item completes, update its checkbox and add the verification evidence to the baseline table.
