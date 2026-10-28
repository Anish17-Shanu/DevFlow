#!/usr/bin/env bash
# End-to-end smoke test against a running DevFlow deployment.
# Usage: scripts/smoke_test.sh <base-url> <api-key>
set -euo pipefail

base_url="${1:?Usage: $0 <base-url> <api-key>}"
api_key="${2:?Usage: $0 <base-url> <api-key>}"
base_url="${base_url%/}"
api="${base_url}/api/v1"

json_field() {
  python3 -c "import json,sys; data=json.load(sys.stdin); print(data$1)"
}

auth=(-H "X-API-Key: ${api_key}" -H "Content-Type: application/json")

echo "[1/6] Liveness and readiness"
curl -fsS "${base_url}/health/live" | grep -q '"status": *"ok"'
ready="$(curl -fsS "${base_url}/health/ready")"
echo "${ready}" | grep -q '"status": *"ok"'
echo "${ready}" | grep -q '"database": *"ok"'

echo "[2/6] Authenticated workflow listing"
curl -fsS "${auth[@]}" "${api}/workflows?limit=1" > /dev/null

echo "[3/6] Creating a smoke workflow"
workflow="$(curl -fsS -X POST "${auth[@]}" "${api}/workflows" -d '{
  "name": "deploy-smoke-test",
  "tasks": [
    {"name": "prepare", "dependencies": [], "config": {"type": "sleep", "duration_ms": 150}},
    {"name": "verify", "dependencies": ["prepare"], "config": {"type": "echo", "message": "smoke ok"}}
  ]
}')"
workflow_id="$(echo "${workflow}" | json_field "['id']")"
echo "  workflow ${workflow_id}"

echo "[4/6] Running the workflow"
execution="$(curl -fsS -X POST "${auth[@]}" "${api}/workflows/${workflow_id}/run")"
execution_id="$(echo "${execution}" | json_field "['id']")"
echo "  execution ${execution_id}"

echo "[5/6] Waiting for success"
for _ in $(seq 1 60); do
  execution="$(curl -fsS "${auth[@]}" "${api}/executions/${execution_id}")"
  status="$(echo "${execution}" | json_field "['status']")"
  case "${status}" in
    success) break ;;
    failed|cancelled) echo "  execution ended ${status}" >&2; exit 1 ;;
  esac
  sleep 1
done
if [[ "${status:-}" != "success" ]]; then
  echo "  execution did not succeed within 60s (last status: ${status:-unknown})" >&2
  exit 1
fi

tasks="$(curl -fsS "${auth[@]}" "${api}/executions/${execution_id}/tasks")"
echo "${tasks}" | grep -q '"status": *"success"'
logs="$(curl -fsS "${auth[@]}" "${api}/executions/${execution_id}/logs?limit=100")"
echo "${logs}" | grep -q '"items"'

echo "[6/6] Queue, metrics, cleanup"
queue="$(curl -fsS "${auth[@]}" "${api}/queue/status")"
echo "${queue}" | grep -q '"healthy": *true'
curl -fsS "${base_url}/metrics" | grep -q 'devflow_http_requests_total'
curl -fsS -X DELETE "${auth[@]}" "${api}/workflows/${workflow_id}" > /dev/null

echo "SMOKE TEST PASSED (${base_url})"
