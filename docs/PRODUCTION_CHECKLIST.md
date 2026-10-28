# Production Release Checklist

Repeatable gate list for shipping DevFlow to a production environment. Copy this checklist into the release PR or issue and attach evidence (CI run link, command output, image digest). Do not promote a build with unchecked boxes.

Related documents: [Deployment Guide](DEPLOYMENT.md) · [Runbook](RUNBOOK.md) · [Security Policy](../SECURITY.md) · [Roadmap](../ROADMAP.md)

---

## 1. Release candidate

- [ ] Version bumped in `backend/core/config.py` (`app_version`) and `frontend/package.json`.
- [ ] `ROADMAP.md` updated for everything included in this release.
- [ ] Changelog/release notes generated from merged PRs.
- [ ] Release branch or tag reviewed by a CODEOWNER.
- [ ] No `TODO`/`FIXME` markers added in touched files without a linked roadmap ID.

## 2. Continuous integration

- [ ] Backend lint and format checks pass on Python 3.12, 3.13, and 3.14.
- [ ] Backend test suite passes with coverage at or above the configured threshold.
- [ ] API documentation drift check passes (`python scripts/generate_api_docs.py --check`).
- [ ] PostgreSQL 16 integration suite passes, including `alembic upgrade → downgrade → upgrade`.
- [ ] Frontend unit tests pass and the production bundle builds.
- [ ] Playwright golden path passes against the built frontend and API.
- [ ] API and web images build, pass Trivy HIGH/CRITICAL scanning, and produce an SBOM.
- [ ] Images are signed with cosign (release tags only).

## 3. Configuration and secrets

- [ ] `DEVFLOW_ENVIRONMENT=production`.
- [ ] `DEVFLOW_DATABASE_URL` points at the production database with TLS where the provider requires it.
- [ ] `DEVFLOW_BOOTSTRAP_API_KEY` is a unique secret of at least 24 characters and is stored in the secret manager.
- [ ] `DEVFLOW_SECRET_ENCRYPTION_KEY` is set (Fernet key) and backed up separately from the database.
- [ ] `DEVFLOW_CORS_ORIGINS` lists only the real frontend origin(s).
- [ ] `DEVFLOW_AUTO_MIGRATE=false`; migrations run as a release job.
- [ ] `DEVFLOW_DOCS_ENABLED=false` unless public docs are intentional.
- [ ] `DEVFLOW_INLINE_WORKERS_ENABLED=false` on API replicas.
- [ ] Worker counts, lease seconds, and retention days reviewed against traffic.
- [ ] No credentials, tokens, or keys exist in committed files (`git grep` spot check).

## 4. Database and data protection

- [ ] Migration tested against a production-like snapshot.
- [ ] Migration is backward compatible with the currently running API/worker version (rolling deploy safe).
- [ ] Pre-deploy backup completed and verified (`scripts/backup_postgres.sh`).
- [ ] Restore drill completed within the last 90 days; RPO/RTO recorded in the runbook.
- [ ] Retention policies confirmed (`log_retention_days`, `execution_retention_days`, `queue_retention_days`, `worker_retention_days`).
- [ ] Disk and connection-pool headroom checked; pool size matches replica count.

## 5. Security

- [ ] TLS certificate valid; HTTP redirects to HTTPS; HSTS present.
- [ ] API keys have the minimum required role (viewer/operator/admin); unused keys revoked.
- [ ] Per-key rate limits and tenant execution limits reviewed.
- [ ] Network policies or security groups block database access from outside the private network.
- [ ] Container images run as non-root with read-only root filesystem where supported.
- [ ] Vulnerability scan results triaged; no unpatched critical finding older than the SLA in [SECURITY.md](../SECURITY.md).
- [ ] Audit log retention and access reviewed for privileged actions.

## 6. Staging verification

- [ ] Staging deployment uses its own database, secrets, and object storage.
- [ ] Staging smoke tests pass (health, login, workflow create/run, logs, metrics).
- [ ] Worker heartbeat health check reports healthy.
- [ ] Queue drains to zero after the smoke run.
- [ ] No new errors in API or worker logs during the smoke window.
- [ ] Production promotion is gated on the green staging run.

## 7. Production rollout

- [ ] Rollout order followed: database → API → workers → frontend.
- [ ] Migration job completed successfully before API rollout.
- [ ] API readiness (`/health/ready`) is `ok` on every replica.
- [ ] Workers register and process a synthetic job.
- [ ] Autoscaling minimums and maximums set; PDBs protect availability.
- [ ] Worker termination grace period exceeds task timeout expectations.
- [ ] Ingress serves API and websocket traffic through one origin.

## 8. Post-deploy verification

- [ ] `GET /health/live` and `GET /health/ready` return `ok`.
- [ ] `GET /metrics` exposes request, queue, worker, and task metrics.
- [ ] Login works with the production API key; RBAC is enforced.
- [ ] Create → run → dashboard → logs golden path works in the browser at 360 px and 1440 px.
- [ ] Execution reaches `succeeded`; queue depth returns to baseline.
- [ ] WebSocket updates arrive, and polling fallback works when the socket is blocked.
- [ ] Alerts are loaded and a test notification reaches the on-call channel.
- [ ] Dashboards show traffic for the new version.
- [ ] Backup job scheduled and first post-deploy backup succeeded.

## 9. Rollback readiness

- [ ] Previous image digests are recorded and pullable.
- [ ] Database migration has a tested downgrade or a forward-fix plan.
- [ ] Rollback command documented in [RUNBOOK.md](RUNBOOK.md).
- [ ] On-call owner and escalation path confirmed.
- [ ] Incident channel opened for the rollout window (high-risk releases).

## 10. Sign-off

| Role | Name | Date | Evidence |
| --- | --- | --- | --- |
| Release owner |  |  |  |
| Backend reviewer |  |  |  |
| Frontend reviewer |  |  |  |
| Security reviewer |  |  |  |
| On-call engineer |  |  |  |

---

## Environment separation

| Setting | Development | Staging | Production |
| --- | --- | --- | --- |
| Database | SQLite file | Isolated PostgreSQL | Managed PostgreSQL with backups |
| API keys | `devflow-dev-key` | Staging-only keys | Secret-manager keys |
| Workers | Inline (default) | Dedicated replicas | Dedicated autoscaled replicas |
| Docs (`/docs`) | Enabled | Enabled | Disabled |
| Auto-migrate | Enabled | Disabled (release job) | Disabled (release job) |
| TLS | Local HTTP | TLS required | TLS required + HSTS |
| Backups | None | Nightly | PITR + nightly dumps |

## Known limitations at this checklist revision

These are tracked in [ROADMAP.md](../ROADMAP.md) and must be considered before promising them to customers:

- Single-region deployment; no tested multi-region failover.
- WebSocket fan-out is per API process; clients fall back to polling when they connect to a different replica.
- Approval gates/checkpoints are not implemented.
- Queue and log tables are not partitioned; retention is the current growth control.
- Load-test capacity numbers are documented in [CAPACITY.md](CAPACITY.md) for a single-node reference environment, not for every production shape.
