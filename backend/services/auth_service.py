from __future__ import annotations

import time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.core.security import ROLE_LEVELS, ApiError, Principal, generate_api_key, hash_api_key, key_prefix
from backend.core.time import utc_now
from backend.models.entities import ApiKey, Tenant
from backend.schemas.auth import ApiKeyCreate

_principal_cache: dict[str, tuple[Principal, float]] = {}


class AuthService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def ensure_bootstrap(self) -> Principal:
        tenant = await self.session.scalar(select(Tenant).where(Tenant.slug == "default"))
        if tenant is None:
            tenant = Tenant(name=settings.bootstrap_tenant_name, slug="default")
            self.session.add(tenant)
            await self.session.flush()

        key_hash = hash_api_key(settings.bootstrap_api_key)
        api_key = await self.session.scalar(select(ApiKey).where(ApiKey.key_hash == key_hash))
        if api_key is None:
            api_key = ApiKey(
                tenant_id=tenant.id,
                name="bootstrap",
                prefix=key_prefix(settings.bootstrap_api_key),
                key_hash=key_hash,
                role="admin",
            )
            self.session.add(api_key)
        await self.session.commit()
        return Principal(
            tenant_id=tenant.id,
            tenant_name=tenant.name,
            key_id=api_key.id,
            key_name=api_key.name,
            role=api_key.role,
        )

    async def authenticate(self, raw_key: str) -> Principal | None:
        if not raw_key:
            return None
        key_hash = hash_api_key(raw_key)
        cached = _principal_cache.get(key_hash)
        now = time.monotonic()
        if cached and cached[1] > now:
            return cached[0]

        row = (
            await self.session.execute(
                select(ApiKey, Tenant)
                .join(Tenant, Tenant.id == ApiKey.tenant_id)
                .where(ApiKey.key_hash == key_hash, ApiKey.revoked_at.is_(None))
            )
        ).first()
        if row is None:
            return None

        api_key, tenant = row
        principal = Principal(
            tenant_id=tenant.id,
            tenant_name=tenant.name,
            key_id=api_key.id,
            key_name=api_key.name,
            role=api_key.role,
        )
        if settings.auth_cache_ttl_seconds:
            _principal_cache[key_hash] = (principal, now + settings.auth_cache_ttl_seconds)
        api_key.last_used_at = utc_now()
        await self.session.commit()
        return principal

    async def create_key(self, principal: Principal, payload: ApiKeyCreate) -> tuple[ApiKey, str]:
        principal.require("admin")
        if payload.role not in ROLE_LEVELS:
            raise ApiError(422, "validation_error", "Unknown role.")
        raw_key = generate_api_key()
        record = ApiKey(
            tenant_id=principal.tenant_id,
            name=payload.name.strip(),
            prefix=key_prefix(raw_key),
            key_hash=hash_api_key(raw_key),
            role=payload.role,
        )
        self.session.add(record)
        await self.session.commit()
        await self.session.refresh(record)
        return record, raw_key

    async def list_keys(self, principal: Principal) -> list[ApiKey]:
        principal.require("admin")
        result = await self.session.execute(
            select(ApiKey).where(ApiKey.tenant_id == principal.tenant_id).order_by(ApiKey.created_at.desc())
        )
        return list(result.scalars())

    async def revoke_key(self, principal: Principal, key_id: str) -> None:
        principal.require("admin")
        record = await self.session.scalar(
            select(ApiKey).where(ApiKey.id == key_id, ApiKey.tenant_id == principal.tenant_id)
        )
        if record is None:
            raise ApiError(404, "not_found", "API key not found.")
        if record.id == principal.key_id:
            raise ApiError(400, "invalid_request", "You cannot revoke the key currently in use.")
        record.revoked_at = utc_now()
        _principal_cache.pop(record.key_hash, None)
        await self.session.commit()
