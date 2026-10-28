from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.dependencies import require_role
from backend.core.database import get_db_session
from backend.core.security import Principal
from backend.schemas.auth import ApiKeyCreate, ApiKeyCreatedResponse, ApiKeyResponse, MeResponse
from backend.services.audit_service import AuditService
from backend.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me", response_model=MeResponse)
async def me(principal: Principal = Depends(require_role("viewer"))):
    return MeResponse(
        tenant_id=principal.tenant_id,
        tenant_name=principal.tenant_name,
        key_id=principal.key_id,
        key_name=principal.key_name,
        role=principal.role,
    )


@router.get("/keys", response_model=list[ApiKeyResponse])
async def list_keys(
    principal: Principal = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_db_session),
):
    return await AuthService(session).list_keys(principal)


@router.post("/keys", response_model=ApiKeyCreatedResponse, status_code=201)
async def create_key(
    payload: ApiKeyCreate,
    principal: Principal = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_db_session),
):
    record, raw_key = await AuthService(session).create_key(principal, payload)
    AuditService.write(
        session,
        principal,
        "api_key.created",
        "api_key",
        record.id,
        {"name": record.name, "role": record.role},
    )
    await session.commit()
    return ApiKeyCreatedResponse(
        id=record.id,
        name=record.name,
        prefix=record.prefix,
        role=record.role,
        created_at=record.created_at,
        last_used_at=record.last_used_at,
        revoked_at=record.revoked_at,
        key=raw_key,
    )


@router.delete("/keys/{key_id}", status_code=204)
async def revoke_key(
    key_id: str,
    principal: Principal = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_db_session),
):
    await AuthService(session).revoke_key(principal, key_id)
    AuditService.write(session, principal, "api_key.revoked", "api_key", key_id)
    await session.commit()
