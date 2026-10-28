from __future__ import annotations

from backend.handlers.base import Handler, HandlerContext, HandlerError
from backend.handlers.builtin import echo_handler, fail_handler, http_handler, sleep_handler


class HandlerRegistry:
    def __init__(self) -> None:
        self._handlers: dict[str, Handler] = {}

    def register(self, name: str, handler: Handler) -> None:
        self._handlers[name] = handler

    def get(self, name: str) -> Handler:
        handler = self._handlers.get(name)
        if handler is None:
            raise HandlerError(f"Unknown task type '{name}'.")
        return handler

    def names(self) -> list[str]:
        return sorted(self._handlers)


registry = HandlerRegistry()
registry.register("sleep", sleep_handler)
registry.register("echo", echo_handler)
registry.register("http", http_handler)
registry.register("fail", fail_handler)

__all__ = ["HandlerContext", "HandlerError", "HandlerRegistry", "registry"]
