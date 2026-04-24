"""Session repository."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel

from ...utils.ids import new_session_id
from ...utils.logging import get_logger
from ..database import Database

logger = get_logger(__name__)


class Session(BaseModel):
    id: str
    conversation_id: str | None
    provider: str
    model: str
    created_at: str
    last_active: str
    is_active: bool


class SessionRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def create(
        self,
        provider: str,
        model: str,
        conversation_id: str | None = None,
    ) -> Session:
        sess_id = new_session_id()
        now = datetime.now(timezone.utc).isoformat()
        await self.db.execute(
            """INSERT INTO sessions (id, conversation_id, provider, model, created_at, last_active, is_active)
               VALUES ($1, $2, $3, $4, $5, $6, TRUE)""",
            (sess_id, conversation_id, provider, model, now, now),
        )
        await self.db.commit()
        return Session(
            id=sess_id, conversation_id=conversation_id, provider=provider,
            model=model, created_at=now, last_active=now, is_active=True,
        )

    async def get(self, session_id: str) -> Session | None:
        row = await self.db.fetchone(
            "SELECT * FROM sessions WHERE id = $1", (session_id,)
        )
        return self._row_to_model(row) if row else None

    async def touch(self, session_id: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        await self.db.execute(
            "UPDATE sessions SET last_active = $1 WHERE id = $2", (now, session_id)
        )
        await self.db.commit()

    async def deactivate(self, session_id: str) -> None:
        await self.db.execute(
            "UPDATE sessions SET is_active = FALSE WHERE id = $1", (session_id,)
        )
        await self.db.commit()

    def _row_to_model(self, row: Any) -> Session:
        return Session(
            id=row["id"],
            conversation_id=row["conversation_id"],
            provider=row["provider"],
            model=row["model"],
            created_at=str(row["created_at"]),
            last_active=str(row["last_active"]),
            is_active=bool(row["is_active"]),
        )
