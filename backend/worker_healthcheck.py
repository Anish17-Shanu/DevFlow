"""Container health probe for the standalone worker process.

Fails when the heartbeat file is missing or older than the allowed age, which
happens when the worker event loop is blocked or the process no longer runs.
"""

from __future__ import annotations

import os
import sys
import time

from backend.workers.heartbeat import heartbeat_path

MAX_AGE_SECONDS = 30.0


def main() -> int:
    configured = os.getenv("DEVFLOW_WORKER_HEARTBEAT_MAX_AGE", "")
    try:
        max_age = float(configured) if configured else MAX_AGE_SECONDS
    except ValueError:
        print(f"Invalid DEVFLOW_WORKER_HEARTBEAT_MAX_AGE={configured!r}", file=sys.stderr)
        return 1

    path = heartbeat_path()
    try:
        age = time.time() - path.stat().st_mtime
    except FileNotFoundError:
        print(f"Worker heartbeat file {path} is missing.", file=sys.stderr)
        return 1

    if age > max_age:
        print(f"Worker heartbeat is stale ({age:.1f}s > {max_age:.1f}s).", file=sys.stderr)
        return 1

    print(f"Worker heartbeat is fresh ({age:.1f}s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
