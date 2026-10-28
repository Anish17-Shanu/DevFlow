from __future__ import annotations

import asyncio
import os
import time

from backend import worker_healthcheck
from backend.workers.heartbeat import heartbeat_path, write_heartbeat_loop


def test_healthcheck_requires_fresh_heartbeat(tmp_path, monkeypatch):
    target = tmp_path / "heartbeat"
    monkeypatch.setenv("DEVFLOW_WORKER_HEARTBEAT_FILE", str(target))

    assert worker_healthcheck.main() == 1

    target.write_text("now", encoding="utf-8")
    assert worker_healthcheck.main() == 0

    stale = time.time() - 120
    os.utime(target, (stale, stale))
    monkeypatch.setenv("DEVFLOW_WORKER_HEARTBEAT_MAX_AGE", "30")
    assert worker_healthcheck.main() == 1


async def test_heartbeat_loop_writes_file(tmp_path, monkeypatch):
    target = tmp_path / "heartbeat"
    monkeypatch.setenv("DEVFLOW_WORKER_HEARTBEAT_FILE", str(target))
    stop_event = asyncio.Event()

    task = asyncio.create_task(write_heartbeat_loop(stop_event, 1))
    await asyncio.sleep(0.05)
    assert heartbeat_path() == target
    assert target.exists()

    stop_event.set()
    await asyncio.wait_for(task, timeout=2)
