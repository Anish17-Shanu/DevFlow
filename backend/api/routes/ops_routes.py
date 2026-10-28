from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.dependencies import get_runtime, require_role
from backend.controllers.ops_controller import OpsController
from backend.core.database import get_db_session
from backend.core.security import Principal
from backend.schemas.ops import (
    AuditLogResponse,
    DeadLetterJobResponse,
    DeadLetterListResponse,
    DiagnosticsResponse,
    SecretCreate,
    SecretResponse,
    WebhookCreate,
    WebhookDeliveryResponse,
    WebhookResponse,
)

router = APIRouter(tags=["operations"])


@router.get("/audit", response_model=dict)
async def list_audit(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    principal: Principal = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_db_session),
):
    controller = OpsController(session)
    result = await controller.list_audit(principal, limit, offset)
    result["items"] = [AuditLogResponse.model_validate(item) for item in result["items"]]
    return result


@router.get("/secrets", response_model=list[SecretResponse])
async def list_secrets(
    principal: Principal = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_db_session),
):
    return await OpsController(session).list_secrets(principal)


@router.post("/secrets", response_model=SecretResponse, status_code=201)
async def create_secret(
    payload: SecretCreate,
    principal: Principal = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_db_session),
):
    return await OpsController(session).create_secret(principal, payload)


@router.delete("/secrets/{name}", status_code=204)
async def delete_secret(
    name: str,
    principal: Principal = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_db_session),
):
    await OpsController(session).delete_secret(principal, name)
    return Response(status_code=204)


@router.get("/webhooks", response_model=list[WebhookResponse])
async def list_webhooks(
    principal: Principal = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_db_session),
):
    return await OpsController(session).list_webhooks(principal)


@router.post("/webhooks", response_model=WebhookResponse, status_code=201)
async def create_webhook(
    payload: WebhookCreate,
    principal: Principal = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_db_session),
):
    return await OpsController(session).create_webhook(principal, payload)


@router.delete("/webhooks/{webhook_id}", status_code=204)
async def delete_webhook(
    webhook_id: str,
    principal: Principal = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_db_session),
):
    await OpsController(session).delete_webhook(principal, webhook_id)
    return Response(status_code=204)


@router.get("/webhooks/deliveries", response_model=dict)
async def list_deliveries(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    principal: Principal = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_db_session),
):
    result = await OpsController(session).list_deliveries(principal, limit, offset)
    result["items"] = [WebhookDeliveryResponse.model_validate(item) for item in result["items"]]
    return result


@router.get("/queue/dead-letters", response_model=DeadLetterListResponse)
async def list_dead_letters(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    principal: Principal = Depends(require_role("admin")),
    runtime=Depends(get_runtime),
    session: AsyncSession = Depends(get_db_session),
):
    controller = OpsController(session, runtime)
    result = await controller.list_dead_letters(principal, limit, offset)
    result["items"] = [DeadLetterJobResponse.model_validate(item) for item in result["items"]]
    return result


@router.post("/queue/dead-letters/{job_id}/replay")
async def replay_dead_letter(
    job_id: str,
    principal: Principal = Depends(require_role("operator")),
    runtime=Depends(get_runtime),
    session: AsyncSession = Depends(get_db_session),
):
    return await OpsController(session, runtime).replay_dead_letter(principal, job_id)


@router.delete("/schedules/{schedule_id}", status_code=204)
async def delete_schedule(
    schedule_id: str,
    principal: Principal = Depends(require_role("operator")),
    session: AsyncSession = Depends(get_db_session),
):
    await OpsController(session).delete_schedule(principal, schedule_id)
    return Response(status_code=204)


@router.get("/diagnostics", response_model=DiagnosticsResponse)
async def diagnostics(
    principal: Principal = Depends(require_role("admin")),
    runtime=Depends(get_runtime),
    session: AsyncSession = Depends(get_db_session),
):
    return await OpsController(session, runtime).diagnostics(principal)
