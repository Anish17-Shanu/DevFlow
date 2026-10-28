from __future__ import annotations

import contextlib
import contextvars
from collections.abc import Iterator

request_id: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")
tenant_id: contextvars.ContextVar[str] = contextvars.ContextVar("tenant_id", default="-")
execution_id: contextvars.ContextVar[str] = contextvars.ContextVar("execution_id", default="-")
task_id: contextvars.ContextVar[str] = contextvars.ContextVar("task_id", default="-")
worker_id: contextvars.ContextVar[str] = contextvars.ContextVar("worker_id", default="-")


def current_context() -> dict[str, str]:
    return {
        "request_id": request_id.get(),
        "tenant_id": tenant_id.get(),
        "execution_id": execution_id.get(),
        "task_id": task_id.get(),
        "worker_id": worker_id.get(),
    }


@contextlib.contextmanager
def binding(**values: str | None) -> Iterator[None]:
    tokens = []
    for name, value in values.items():
        variable = globals().get(name)
        if isinstance(variable, contextvars.ContextVar) and value is not None:
            tokens.append((variable, variable.set(value)))
    try:
        yield
    finally:
        for variable, token in reversed(tokens):
            variable.reset(token)
