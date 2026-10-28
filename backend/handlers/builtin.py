from __future__ import annotations

import asyncio
import ipaddress
from urllib.parse import urlparse

import httpx

from backend.core.config import settings
from backend.handlers.base import HandlerContext, HandlerError
from backend.services.secret_service import SECRET_PATTERN


def _validate_outbound_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise HandlerError("Only http and https URLs are allowed.")
    host = (parsed.hostname or "").lower()
    if not host:
        raise HandlerError("URL must include a hostname.")
    if host in {"localhost", "metadata.google.internal"} or host.endswith(".local"):
        raise HandlerError("Private network targets are not allowed.")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return
    if address.is_private or address.is_loopback or address.is_link_local or address.is_reserved:
        raise HandlerError("Private network targets are not allowed.")


async def sleep_handler(context: HandlerContext) -> dict:
    duration_ms = int(context.config.get("duration_ms", 800))
    await asyncio.sleep(duration_ms / 1000)
    return {"duration_ms": duration_ms}


async def echo_handler(context: HandlerContext) -> dict:
    message = context.config.get("message") or f"Task '{context.task_name}' completed."
    return {"message": message}


async def http_handler(context: HandlerContext) -> dict:
    url = context.config.get("url") or ""
    if not settings.allow_private_task_targets:
        _validate_outbound_url(url)
    headers = {
        name: await context.secrets.render_template(context.tenant_id, value)
        for name, value in (context.config.get("headers") or {}).items()
    }
    body = context.config.get("body")
    if body:
        body = await context.secrets.render_template(context.tenant_id, body)

    timeout = float(context.config.get("timeout_seconds", 60))
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
            response = await client.request(
                context.config.get("method", "GET"),
                url,
                headers=headers,
                content=body.encode("utf-8") if body else None,
            )
    except httpx.HTTPError as exc:
        raise HandlerError(f"HTTP request failed: {exc.__class__.__name__}.") from exc

    expected = context.config.get("expected_status")
    if expected and response.status_code != expected:
        raise HandlerError(f"HTTP task expected status {expected} but received {response.status_code}.")
    if not expected and response.status_code >= 400:
        raise HandlerError(f"HTTP task received status {response.status_code}.")
    return {"status_code": response.status_code, "body_preview": response.text[:500]}


async def fail_handler(context: HandlerContext) -> dict:
    raise HandlerError(context.config.get("message") or "Task intentionally failed.")


def secret_names_in(config: dict) -> list[str]:
    names: list[str] = []
    for value in [config.get("url") or "", config.get("body") or "", *(config.get("headers") or {}).values()]:
        names.extend(SECRET_PATTERN.findall(value))
    return sorted(set(names))


__all__ = [
    "echo_handler",
    "fail_handler",
    "http_handler",
    "sleep_handler",
]
