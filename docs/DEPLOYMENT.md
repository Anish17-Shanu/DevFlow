# Deployment Guide

DevFlow ships as three processes — API, worker, and web — plus PostgreSQL. This guide
covers local Compose deployment and a production Kubernetes deployment.

For incident procedures see [RUNBOOK.md](RUNBOOK.md); for the release gate list see
[PRODUCTION_CHECKLIST.md](PRODUCTION_CHECKLIST.md).

## Prerequisites

- Docker Engine with Compose v2 (local and single-host deployments).
- Kubernetes 1.28+ with an ingress controller and cert-manager (cluster deployments).
- PostgreSQL 16 (managed service recommended).
- A secret store: External Secrets, Sealed Secrets, or the cloud provider's manager.

## Required secrets

Production refuses to start unless these are set:

| Variable | Purpose |
| --- | --- |
| `DEVFLOW_BOOTSTRAP_API_KEY` | initial admin key; unique, at least 24 characters |
| `DEVFLOW_SECRET_ENCRYPTION_KEY` | Fernet key for tenant secrets |
| `DEVFLOW_DATABASE_URL` | database connection string |
| `POSTGRES_PASSWORD` | Compose only; included in the database URL |

Generate values:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

`DEVFLOW_AUTO_MIGRATE` must be `false` in production. Migrations run as a release job.

## Compose deployment

```bash
cp .env.example .env
# edit .env: set POSTGRES_PASSWORD, DEVFLOW_BOOTSTRAP_API_KEY, DEVFLOW_SECRET_ENCRYPTION_KEY
docker compose up -d --build
docker compose ps
```

Services and ports:

| Service | Port | Notes |
| --- | --- | --- |
| `web` | 8080 | public entry point; proxies `/api`, `/ws`, `/health`, `/metrics` |
| `api` | 127.0.0.1:8000 | bound to loopback for debugging |
| `postgres` | internal | no host port |
| `migrate` | — | one-shot `alembic upgrade head`, runs before API/worker |
| `worker` | — | no inbound traffic |

The `migrate` service uses `service_completed_successfully`; API and worker start only
after migrations succeed. All services have health checks, log rotation, resource limits,
and `no-new-privileges`.

Verify:

```bash
curl -fsS http://127.0.0.1:8080/health/ready
curl -fsS http://127.0.0.1:8080/healthz
docker compose exec worker python -m backend.worker_healthcheck
```

## TLS

Terminate TLS at an ingress or reverse proxy and keep the web container internal. The
sample [deploy/nginx/tls.conf](../deploy/nginx/tls.conf) redirects HTTP to HTTPS, adds
HSTS and security headers, and forwards WebSocket upgrades. Mount certificates from
certbot or your platform's certificate manager.

In Kubernetes, [deploy/k8s/ingress.yaml](../deploy/k8s/ingress.yaml) requests a
certificate with `cert-manager.io/cluster-issuer` and forces SSL redirect. CORS is
unnecessary because the UI and API share an origin.

## Kubernetes deployment

1. Create the namespace and secrets:

   ```bash
   kubectl apply -f deploy/k8s/namespace.yaml
   kubectl create secret generic devflow-secrets -n devflow \
     --from-literal=DEVFLOW_BOOTSTRAP_API_KEY="$BOOTSTRAP_KEY" \
     --from-literal=DEVFLOW_SECRET_ENCRYPTION_KEY="$FERNET_KEY" \
     --from-literal=POSTGRES_PASSWORD="$DB_PASSWORD" \
     --from-literal=DEVFLOW_DATABASE_URL="$DATABASE_URL"
   ```

2. Set the image registry and host:

   ```bash
   # deploy/k8s/kustomization.yaml: images[].newName
   # deploy/k8s/ingress.yaml: host and TLS secret
   kubectl apply -k deploy/k8s
   ```

Manifests include:

- API and web Deployments with readiness/liveness/startup probes, rolling updates with
  `maxUnavailable: 0`, HPAs, and PodDisruptionBudgets.
- A worker Deployment with a 45 s termination grace period, heartbeat-based probes, and
  a unique `DEVFLOW_WORKER_INSTANCE_ID` from the pod name.
- A migration Job annotated as an Argo CD PreSync hook; run it as a pre-deploy step in
  other pipelines.
- A PostgreSQL StatefulSet for evaluation. Use a managed database in production.
- Default-deny network policies plus explicit allowances between web, api, worker,
  migrate, database, DNS, and egress for HTTP task handlers/webhooks.

Scale workers on queue depth with KEDA:

```yaml
triggers:
  - type: prometheus
    metadata:
      serverAddress: http://prometheus.monitoring:9090
      metricName: devflow_queue_depth
      query: max(devflow_queue_depth)
      threshold: "20"
```

## Migration policy

- Every schema change adds an Alembic revision under `migrations/versions/`.
- CI applies `upgrade head`, `downgrade base`, then `upgrade head` against PostgreSQL 16.
- The release job runs `alembic upgrade head` before new API/worker pods start.
- Migrations are forward-only in production; roll back application images, not schemas,
  unless a tested down migration exists.

## Observability

- Scrape `/metrics` from API pods (annotations are already set).
- Load [alerts.yml](../deploy/observability/alerts.yml) into Prometheus and import
  [grafana-dashboard.json](../deploy/observability/grafana-dashboard.json).
- Structured JSON logs go to stdout; ship them with your platform's log agent.
- Set `DEVFLOW_OTEL_EXPORTER_OTLP_ENDPOINT` to enable tracing (requires the optional
  OpenTelemetry packages).

## Scaling guidance

| Component | Signal | Notes |
| --- | --- | --- |
| API | CPU, request rate | stateless; requires shared realtime bus for perfect multi-replica sockets |
| Worker | queue depth, CPU | set `DEVFLOW_WORKER_COUNT` per pod; scale pods with KEDA |
| Database | connections, write latency | keep total pool size under the server limit |
| Web | request rate | static assets behind CDN |

Capacity targets must be measured (ROADMAP SCALE-01) with the load tests described in
`docs/OPERATIONS.md`. Treat the numbers in the roadmap as targets, not guarantees.

## Backups

- Managed PostgreSQL: enable automated daily snapshots and continuous WAL archiving.
- Compose: schedule [scripts/backup_postgres.sh](../scripts/backup_postgres.sh) and copy
  the archives off-host. Restore with
  [scripts/restore_postgres.sh](../scripts/restore_postgres.sh) (requires `--yes`).
- Run the restore drill in [RUNBOOK.md](RUNBOOK.md#backup-and-restore-drill) monthly.

## Rollback

1. Re-deploy the previous image tags.
2. Confirm `/health/ready` and worker heartbeats.
3. Run one golden-path execution.
4. If a migration is incompatible with the previous image, roll forward with a fix
   instead of downgrading the schema.

## Environment checklist

- [ ] `DEVFLOW_ENVIRONMENT=production`
- [ ] `DEVFLOW_AUTO_MIGRATE=false`
- [ ] `DEVFLOW_INLINE_WORKERS_ENABLED=false`
- [ ] `DEVFLOW_DOCS_ENABLED=false` unless docs are intentionally public
- [ ] `DEVFLOW_CORS_ORIGINS` matches the public origin
- [ ] `DEVFLOW_DATABASE_POOL_SIZE × replicas` is below the database connection limit
- [ ] `DEVFLOW_REALTIME_BUS=auto` (default) so websocket updates fan out across API replicas over Postgres `LISTEN/NOTIFY`
- [ ] `DEVFLOW_QUEUE_LEASE_SECONDS` exceeds the heartbeat interval by a wide margin
- [ ] `DEVFLOW_WORKER_SHUTDOWN_GRACE_SECONDS` is shorter than the orchestrator grace period
- [ ] Secrets come from a secret manager, not an image or repository
- [ ] Ingress forces HTTPS and the certificate is valid
- [ ] Metrics are scraped and alerts route to the on-call channel
- [ ] Backups are configured and a restore has been drilled
