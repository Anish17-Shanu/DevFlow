from __future__ import annotations

from fastapi import Depends, Request, WebSocket
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.context import tenant_id as tenant_context
from backend.core.database import get_db_session
from backend.core.rate_limit import rate_limiter
from backend.core.security import ApiError, Principal
from backend.services.auth_service import AuthService


def extract_api_key(request: Request) -> str:
    header_key = request.headers.get("x-api-key")
    if header_key:
        return header_key.strip()
    authorization = request.headers.get("authorization", "")
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return ""


async def get_principal(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> Principal:
    raw_key = extract_api_key(request)
    if not raw_key:
        raise ApiError(401, "unauthorized", "Provide an API key via X-API-Key or Authorization: Bearer.")
    principal = await AuthService(session).authenticate(raw_key)
    if principal is None:
        raise ApiError(401, "unauthorized", "Invalid or revoked API key.")
    allowed, retry_after = await rate_limiter.consume(principal.key_id)
    if not allowed:
        raise ApiError(429, "rate_limited", "Rate limit exceeded.", headers={"Retry-After": str(retry_after)})
    tenant_context.set(principal.tenant_id)
    return principal


def require_role(minimum: str):
    async def dependency(principal: Principal = Depends(get_principal)) -> Principal:
        principal.require(minimum)
        return principal

    return dependency


async def authenticate_websocket(websocket: WebSocket) -> Principal | None:
    raw_key = websocket.query_params.get("api_key") or ""
    if not raw_key:
        raw_key = websocket.headers.get("x-api-key", "")
    if not raw_key:
        await websocket.close(code=1008, reason="Missing API key.")
        return None

    from backend.core.database import SessionLocal

    async with SessionLocal() as session:
        principal = await AuthService(session).authenticate(raw_key)
    if principal is None:
        await websocket.close(code=1008, reason="Invalid API key.")
        return None
    tenant_context.set(principal.tenant_id)
    return principal


def get_execution_service(request: Request):
    return request.app.state.runtime.execution_service


def get_worker_manager(request: Request):
    return request.app.state.runtime.worker_manager


def get_queue(request: Request):
    return request.app.state.runtime.queue


def get_realtime(request: Request):
    return request.app.state.runtime.realtime


def get_runtime(request: Request):
    return request.app.state.runtime
