#!/usr/bin/env bash
# Restore a logical Postgres backup into the Compose database.
# DESTRUCTIVE: drops and recreates objects in the devflow database.
# Usage: scripts/restore_postgres.sh <backup.dump> --yes
set -euo pipefail

if [[ $# -lt 2 || "${2}" != "--yes" ]]; then
  echo "Usage: $0 <backup.dump> --yes" >&2
  echo "This replaces the current devflow database. Stop api/worker first." >&2
  exit 1
fi

backup="$1"
if [[ ! -s "${backup}" ]]; then
  echo "Backup file ${backup} is missing or empty." >&2
  exit 1
fi

echo "Stopping api and worker to release database connections"
docker compose stop api worker

echo "Restoring ${backup}"
docker compose exec -T postgres pg_restore -U devflow -d devflow --clean --if-exists --no-owner --no-privileges < "${backup}"

echo "Starting api and worker"
docker compose start api worker

echo "Restore complete. Verify with: curl -fsS http://127.0.0.1:8000/health/ready"
