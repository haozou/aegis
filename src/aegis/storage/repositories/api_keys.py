"""API key repository."""

from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from ...utils.ids import new_api_key_id
from ...utils.logging import get_logger
from ..database import Database

logger = get_logger(__name__)


class ApiKey(BaseModel):
    id: str
    user_id: str
    key_prefix: str
    name: str = "default"
    scopes: list[str] = Field(default_factory=lambda: ["agent:read", "agent:write", "agent:execute"])
    last_used: str | None = None
    expires_at: str | None = None
    is_active: bool = True
    created_at: str


class ApiKeyWithSecret(BaseModel):
    """Returned only on creation — includes the full key."""
    api_key: ApiKey
    secret: str  # the full key, shown once


class ApiKeyRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    @staticmethod
    def generate_key() -> tuple[str, str, str]:
        """Generate a new API key. Returns (full_key, key_hash, key_prefix)."""
        raw = secrets.token_urlsafe(32)
        full_key = f"ak_{raw}"
        key_hash = hashlib.sha256(full_key.encode()).hexdigest()
        key_prefix = full_key[:12]
        return full_key, key_hash, key_prefix

    async def create(
        self, user_id: str, name: str = "default",
        scopes: list[str] | None = None,
    ) -> ApiKeyWithSecret:
        key_id = new_api_key_id()
        full_key, key_hash, key_prefix = self.generate_key()
        now = datetime.now(timezone.utc).isoformat()
        scopes = scopes or ["agent:read", "agent:write", "agent:execute"]

        await self.db.execute(
            """INSERT INTO api_keys (id, user_id, key_hash, key_prefix, name, scopes, created_at)
               VALUES ($1, $2, $3, $4, $5, $6, $7)""",
            (key_id, user_id, key_hash, key_prefix, name, json.dumps(scopes), now),
        )
        await self.db.commit()

        api_key = ApiKey(
            id=key_id, user_id=user_id, key_prefix=key_prefix,
            name=name, scopes=scopes, created_at=now,
        )
        return ApiKeyWithSecret(api_key=api_key, secret=full_key)

    async def verify(self, full_key: str) -> ApiKey | None:
        """Verify an API key and return the ApiKey if valid."""
        key_hash = hashlib.sha256(full_key.encode()).hexdigest()
        row = await self.db.fetchone(
            "SELECT * FROM api_keys WHERE key_hash = $1 AND is_active = TRUE",
            (key_hash,),
        )
        if row is None:
            return None

        # Update last_used
        now = datetime.now(timezone.utc).isoformat()
        await self.db.execute(
            "UPDATE api_keys SET last_used = $1 WHERE id = $2", (now, row["id"])
        )
        await self.db.commit()

        return self._row_to_model(row)

    async def list_by_user(self, user_id: str) -> list[ApiKey]:
        rows = await self.db.fetchall(
            "SELECT * FROM api_keys WHERE user_id = $1 AND is_active = TRUE ORDER BY created_at DESC",
            (user_id,),
        )
        return [self._row_to_model(r) for r in rows]

    async def revoke(self, key_id: str, user_id: str) -> bool:
        row = await self.db.fetchone(
            "SELECT * FROM api_keys WHERE id = $1 AND user_id = $2", (key_id, user_id),
        )
        if row is None:
            return False
        await self.db.execute(
            "UPDATE api_keys SET is_active = FALSE WHERE id = $1", (key_id,)
        )
        await self.db.commit()
        return True

    def _row_to_model(self, row: Any) -> ApiKey:
        scopes = row["scopes"]
        if isinstance(scopes, str):
            try:
                scopes = json.loads(scopes)
            except (json.JSONDecodeError, TypeError):
                scopes = []
        return ApiKey(
            id=row["id"],
            user_id=row["user_id"],
            key_prefix=row["key_prefix"],
            name=row["name"],
            scopes=scopes or [],
            last_used=str(row["last_used"]) if row["last_used"] else None,
            expires_at=str(row["expires_at"]) if row["expires_at"] else None,
            is_active=bool(row["is_active"]),
            created_at=str(row["created_at"]),
        )
