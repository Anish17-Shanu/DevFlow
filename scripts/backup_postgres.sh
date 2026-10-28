#!/usr/bin/env bash
# Logical Postgres backup for the Compose deployment.
# Usage: scripts/backup_postgres.sh [output-directory]
# Env: COMPOSE_FILE (default docker-compose.yml), BACKUP_RETENTION_DAYS (default 14)
set -euo pipefail

output_dir="${1:-backups}"
retention_days="${BACKUP_RETENTION_DAYS:-14}"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
target="${output_dir}/devflow-${timestamp}.dump"

mkdir -p "${output_dir}"

echo "Writing ${target}"
docker compose exec -T postgres pg_dump -U devflow -d devflow --format=custom --no-owner --no-privileges > "${target}"

if [[ ! -s "${target}" ]]; then
  echo "Backup failed: ${target} is empty." >&2
  exit 1
fi

echo "Backup size: $(du -h "${target}" | cut -f1)"
echo "Verifying archive can be listed"
docker compose exec -T postgres pg_restore --list < "${target}" > /dev/null

find "${output_dir}" -name 'devflow-*.dump' -type f -mtime "+${retention_days}" -print -delete
echo "Backup complete. Retention: ${retention_days} days."
