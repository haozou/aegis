"""Conversation repository."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from ...utils.errors import ConversationNotFoundError
from ...utils.ids import new_conversation_id
from ...utils.logging import get_logger
from ..database import Database

logger = get_logger(__name__)


class ConversationCreate(BaseModel):
    title: str = "New Conversation"
    provider: str = "anthropic"
    model: str = "claude-sonnet-4-5"
    system_prompt: str | None = None
    user_id: str | None = None
    agent_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConversationUpdate(BaseModel):
    title: str | None = None
    provider: str | None = None
    model: str | None = None
    system_prompt: str | None = None
    metadata: dict[str, Any] | None = None


class Conversation(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str
    provider: str
    model: str
    system_prompt: str | None = None
    user_id: str | None = None
    agent_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConversationRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def create(self, data: ConversationCreate) -> Conversation:
        conv_id = new_conversation_id()
        now = datetime.now(timezone.utc).isoformat()
        await self.db.execute(
            """INSERT INTO conversations (id, title, created_at, updated_at, provider, model, system_prompt, user_id, agent_id, metadata)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)""",
            (conv_id, data.title, now, now, data.provider, data.model,
             data.system_prompt, data.user_id, data.agent_id, json.dumps(data.metadata)),
        )
        await self.db.commit()
        return Conversation(
            id=conv_id, title=data.title, created_at=now, updated_at=now,
            provider=data.provider, model=data.model,
            system_prompt=data.system_prompt, user_id=data.user_id,
            agent_id=data.agent_id, metadata=data.metadata,
        )

    async def get(self, conv_id: str) -> Conversation:
        row = await self.db.fetchone(
            "SELECT * FROM conversations WHERE id = $1", (conv_id,)
        )
        if row is None:
            raise ConversationNotFoundError(f"Conversation {conv_id!r} not found")
        return self._row_to_model(row)

    async def list_all(
        self,
        limit: int = 100,
        offset: int = 0,
        user_id: str | None = None,
        agent_id: str | None = None,
    ) -> list[Conversation]:
        if user_id and agent_id:
            rows = await self.db.fetchall(
                "SELECT * FROM conversations WHERE user_id = $1 AND agent_id = $2 ORDER BY updated_at DESC LIMIT $3 OFFSET $4",
                (user_id, agent_id, limit, offset),
            )
        elif user_id:
            rows = await self.db.fetchall(
                "SELECT * FROM conversations WHERE user_id = $1 ORDER BY updated_at DESC LIMIT $2 OFFSET $3",
                (user_id, limit, offset),
            )
        else:
            rows = await self.db.fetchall(
                "SELECT * FROM conversations ORDER BY updated_at DESC LIMIT $1 OFFSET $2",
                (limit, offset),
            )
        return [self._row_to_model(r) for r in rows]

    async def update(self, conv_id: str, data: ConversationUpdate) -> Conversation:
        existing = await self.get(conv_id)
        now = datetime.now(timezone.utc).isoformat()
        updates: dict[str, Any] = {"updated_at": now}
        if data.title is not None:
            updates["title"] = data.title
        if data.provider is not None:
            updates["provider"] = data.provider
        if data.model is not None:
            updates["model"] = data.model
        if data.system_prompt is not None:
            updates["system_prompt"] = data.system_prompt
        if data.metadata is not None:
            updates["metadata"] = json.dumps(data.metadata)

        parts = []
        values: list[Any] = []
        for i, (k, v) in enumerate(updates.items(), 1):
            parts.append(f"{k} = ${i}")
            values.append(v)
        values.append(conv_id)
        set_clause = ", ".join(parts)
        await self.db.execute(
            f"UPDATE conversations SET {set_clause} WHERE id = ${len(values)}", tuple(values)
        )
        await self.db.commit()
        return await self.get(conv_id)

    async def delete(self, conv_id: str) -> None:
        await self.get(conv_id)
        await self.db.execute("DELETE FROM conversations WHERE id = $1", (conv_id,))
        await self.db.commit()

    async def touch(self, conv_id: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        await self.db.execute(
            "UPDATE conversations SET updated_at = $1 WHERE id = $2", (now, conv_id)
        )
        await self.db.commit()

    def _row_to_model(self, row: Any) -> Conversation:
        metadata = row["metadata"]
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except (json.JSONDecodeError, TypeError):
                metadata = {}
        return Conversation(
            id=row["id"],
            title=row["title"],
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            provider=row["provider"],
            model=row["model"],
            system_prompt=row["system_prompt"],
            user_id=row.get("user_id") if isinstance(row, dict) else (row["user_id"] if "user_id" in row.keys() else None),
            agent_id=row.get("agent_id") if isinstance(row, dict) else (row["agent_id"] if "agent_id" in row.keys() else None),
            metadata=metadata or {},
        )
