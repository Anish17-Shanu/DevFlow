"""Small dependency-free load probe for a running DevFlow API.

Examples:
    python scripts/load_test.py --api-key devflow-dev-key --duration 10 --concurrency 20
    python scripts/load_test.py --api-key devflow-dev-key --run-executions 100 --concurrency 10

The script deliberately measures the HTTP surface and queue drain time; it is not a
replacement for a distributed load generator, but it produces repeatable numbers for
the reference environment documented in docs/CAPACITY.md.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
import statistics
import time
from dataclasses import dataclass, field

import httpx


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * fraction)))
    return ordered[index]


@dataclass
class Result:
    latencies: list[float] = field(default_factory=list)
    statuses: dict[int, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def record(self, status: int, seconds: float, error: str = "") -> None:
        self.latencies.append(seconds)
        self.statuses[status] = self.statuses.get(status, 0) + 1
        if error:
            self.errors.append(error)

    def summary(self, duration: float) -> dict:
        total = len(self.latencies)
        return {
            "requests": total,
            "requests_per_second": round(total / duration, 1) if duration else 0,
            "error_rate": round(len(self.errors) / total, 4) if total else 0,
            "statuses": self.statuses,
            "latency_ms": {
                "p50": round(statistics.median(self.latencies) * 1000, 1) if total else 0,
                "p95": round(percentile(self.latencies, 0.95) * 1000, 1) if total else 0,
                "p99": round(percentile(self.latencies, 0.99) * 1000, 1) if total else 0,
            },
        }


async def read_worker(
    client: httpx.AsyncClient,
    url: str,
    headers: dict[str, str],
    stop_at: float,
    result: Result,
) -> None:
    while time.perf_counter() < stop_at:
        started = time.perf_counter()
        try:
            response = await client.get(url, headers=headers)
            result.record(response.status_code, time.perf_counter() - started)
        except Exception as exc:  # noqa: BLE001 - probe records any transport failure
            result.record(0, time.perf_counter() - started, exc.__class__.__name__)


async def run_worker(
    client: httpx.AsyncClient,
    url: str,
    headers: dict[str, str],
    counter: list[int],
    target: int,
    lock: asyncio.Lock,
    result: Result,
) -> None:
    while True:
        async with lock:
            if counter[0] >= target:
                return
            counter[0] += 1
        started = time.perf_counter()
        try:
            response = await client.post(url, headers=headers)
            result.record(response.status_code, time.perf_counter() - started)
        except Exception as exc:  # noqa: BLE001 - probe records any transport failure
            result.record(0, time.perf_counter() - started, exc.__class__.__name__)


async def ensure_workflow(client: httpx.AsyncClient, api: str, headers: dict[str, str]) -> str:
    response = await client.post(
        f"{api}/workflows",
        headers=headers,
        json={
            "name": f"load-test-{int(time.time())}",
            "tasks": [
                {"name": "a", "dependencies": [], "config": {"type": "sleep", "duration_ms": 100}},
                {"name": "b", "dependencies": ["a"], "config": {"type": "sleep", "duration_ms": 100}},
            ],
        },
    )
    response.raise_for_status()
    return response.json()["id"]


async def measure_reads(args, headers: dict[str, str]) -> dict:
    limits = httpx.Limits(max_connections=args.concurrency * 2, max_keepalive_connections=args.concurrency)
    result = Result()
    async with httpx.AsyncClient(base_url=args.base_url, timeout=30, limits=limits) as client:
        await wait_ready(client, headers)
        started = time.perf_counter()
        stop_at = started + args.duration
        await asyncio.gather(
            *[
                read_worker(client, f"{args.api}/workflows?limit=20", headers, stop_at, result)
                for _ in range(args.concurrency)
            ]
        )
        elapsed = time.perf_counter() - started
    return {"mode": "read", "duration_seconds": round(elapsed, 2), **result.summary(elapsed)}


async def measure_runs(args, headers: dict[str, str]) -> dict:
    limits = httpx.Limits(max_connections=args.concurrency * 2, max_keepalive_connections=args.concurrency)
    async with httpx.AsyncClient(base_url=args.base_url, timeout=60, limits=limits) as client:
        await wait_ready(client, headers)
        workflow_id = await ensure_workflow(client, args.api, headers)
        result = Result()
        counter = [0]
        lock = asyncio.Lock()
        started = time.perf_counter()
        await asyncio.gather(
            *[
                run_worker(
                    client,
                    f"{args.api}/workflows/{workflow_id}/run",
                    headers,
                    counter,
                    args.run_executions,
                    lock,
                    result,
                )
                for _ in range(args.concurrency)
            ]
        )
        submit_elapsed = time.perf_counter() - started

        drain_started = time.perf_counter()
        deadline = drain_started + args.max_drain_seconds
        while time.perf_counter() < deadline:
            queue = (await client.get(f"{args.api}/queue/status", headers=headers)).json()
            if queue["queued_jobs"] == 0 and queue["in_flight_jobs"] == 0:
                break
            await asyncio.sleep(0.25)
        drain_elapsed = time.perf_counter() - drain_started
        executions = (await client.get(f"{args.api}/executions?status=success&limit=1", headers=headers)).json()
        failed = (await client.get(f"{args.api}/executions?status=failed&limit=1", headers=headers)).json()

    submitted = sum(result.statuses.get(code, 0) for code in (200, 201))
    return {
        "mode": "run",
        "submitted": submitted,
        "submit_duration_seconds": round(submit_elapsed, 2),
        "submit_throughput_per_second": round(submitted / submit_elapsed, 1) if submit_elapsed else 0,
        "drain_seconds": round(drain_elapsed, 2),
        "succeeded_total": executions.get("total", 0),
        "failed_total": failed.get("total", 0),
        **result.summary(submit_elapsed),
    }


async def wait_ready(client: httpx.AsyncClient, headers: dict[str, str], seconds: float = 30) -> None:
    deadline = time.perf_counter() + seconds
    while time.perf_counter() < deadline:
        try:
            response = await client.get("/health/ready", headers=headers)
            if response.status_code == 200:
                return
        except httpx.HTTPError:
            pass
        await asyncio.sleep(0.25)
    raise SystemExit("API did not become ready in time.")


async def main_async(args) -> dict:
    headers = {"X-API-Key": args.api_key}
    if args.mode == "read":
        result = await measure_reads(args, headers)
    else:
        result = await measure_runs(args, headers)
    result["environment"] = {
        "platform": platform.platform(),
        "cpu_count": os.cpu_count(),
        "python": platform.python_version(),
        "database": args.database,
        "worker_count": args.worker_count,
        "concurrency": args.concurrency,
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--api-key", default=os.environ.get("DEVFLOW_BOOTSTRAP_API_KEY", "devflow-dev-key"))
    parser.add_argument("--mode", choices=["read", "run"], default="read")
    parser.add_argument("--duration", type=float, default=10.0)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--run-executions", type=int, default=100)
    parser.add_argument("--max-drain-seconds", type=float, default=120.0)
    parser.add_argument("--database", default=os.environ.get("DEVFLOW_DATABASE_URL", "sqlite"))
    parser.add_argument("--worker-count", default=os.environ.get("DEVFLOW_WORKER_COUNT", "?"))
    args = parser.parse_args()
    args.api = "/api/v1"
    print(json.dumps(asyncio.run(main_async(args)), indent=2))


if __name__ == "__main__":
    main()
