from __future__ import annotations

import re

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select

from backend.core.config import settings
from backend.core.security import ApiError, derive_fernet_key
from backend.core.time import utc_now
from backend.models.entities import SecretRecord
from backend.schemas.ops import SecretCreate

SECRET_PATTERN = re.compile(r"\{\{secret:([A-Za-z0-9_.-]+)\}\}")


def _fernet() -> Fernet:
    key = settings.secret_encryption_key or settings.bootstrap_api_key
    candidate = key if key.endswith("=") and len(key) == 44 else derive_fernet_key(key)
    return Fernet(candidate.encode("ascii"))


class SecretService:
    def __init__(self, session):
        self.session = session

    async def create(self, tenant_id: str, payload: SecretCreate) -> SecretRecord:
        record = await self.session.scalar(
            select(SecretRecord).where(SecretRecord.tenant_id == tenant_id, SecretRecord.name == payload.name)
        )
        ciphertext = _fernet().encrypt(payload.value.encode("utf-8")).decode("ascii")
        if record is None:
            record = SecretRecord(tenant_id=tenant_id, name=payload.name, ciphertext=ciphertext)
            self.session.add(record)
        else:
            record.ciphertext = ciphertext
            record.updated_at = utc_now()
        await self.session.commit()
        await self.session.refresh(record)
        return record

    async def list(self, tenant_id: str) -> list[SecretRecord]:
        result = await self.session.execute(
            select(SecretRecord).where(SecretRecord.tenant_id == tenant_id).order_by(SecretRecord.name.asc())
        )
        return list(result.scalars())

    async def delete(self, tenant_id: str, name: str) -> None:
        record = await self.session.scalar(
            select(SecretRecord).where(SecretRecord.tenant_id == tenant_id, SecretRecord.name == name)
        )
        if record is None:
            raise ApiError(404, "not_found", "Secret not found.")
        await self.session.delete(record)
        await self.session.commit()

    async def resolve(self, tenant_id: str, name: str) -> str:
        record = await self.session.scalar(
            select(SecretRecord).where(SecretRecord.tenant_id == tenant_id, SecretRecord.name == name)
        )
        if record is None:
            raise ApiError(400, "secret_missing", f"Secret '{name}' is not configured for this tenant.")
        try:
            return _fernet().decrypt(record.ciphertext.encode("ascii")).decode("utf-8")
        except InvalidToken as exc:
            raise ApiError(400, "secret_unreadable", f"Secret '{name}' cannot be decrypted.") from exc

    async def render_template(self, tenant_id: str, value: str) -> str:
        names = SECRET_PATTERN.findall(value)
        for name in names:
            value = value.replace(f"{{{{secret:{name}}}}}", await self.resolve(tenant_id, name))
        return value
