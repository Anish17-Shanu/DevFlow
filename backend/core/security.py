from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException

ROLE_LEVELS = {"viewer": 1, "operator": 2, "admin": 3}


class ApiError(HTTPException):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: Any = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(status_code=status_code, detail=message, headers=headers)
        self.code = code
        self.message = message
        self.details = details


@dataclass(frozen=True)
class Principal:
    tenant_id: str
    tenant_name: str
    key_id: str
    key_name: str
    role: str

    @property
    def level(self) -> int:
        return ROLE_LEVELS.get(self.role, 0)

    def require(self, minimum: str) -> None:
        if self.level < ROLE_LEVELS[minimum]:
            raise ApiError(403, "forbidden", f"This action requires the '{minimum}' role.")


def generate_api_key() -> str:
    return f"dvf_{secrets.token_urlsafe(32)}"


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def key_prefix(raw_key: str) -> str:
    return raw_key[:12]


def derive_fernet_key(secret: str) -> str:
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii")


def verify_signature(secret: str, payload: bytes, signature: str) -> bool:
    expected = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
