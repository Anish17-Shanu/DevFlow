from __future__ import annotations

import asyncio
import logging
import os
import tempfile
import time
from pathlib import Path

logger = logging.getLogger(__name__)


def heartbeat_path() -> Path:
    configured = os.getenv("DEVFLOW_WORKER_HEARTBEAT_FILE", "").strip()
    if configured:
        return Path(configured)
    return Path(tempfile.gettempdir()) / "devflow-worker-heartbeat"


async def write_heartbeat_loop(stop_event: asyncio.Event, interval_seconds: float) -> None:
    path = heartbeat_path()
    interval = max(1.0, interval_seconds)
    while not stop_event.is_set():
        try:
            path.write_text(str(time.time()), encoding="utf-8")
        except OSError:
            logger.exception("Unable to write worker heartbeat file at %s", path)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except TimeoutError:
            continue
