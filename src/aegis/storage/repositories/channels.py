"""Channel connections repository."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from ...utils.ids import new_id
from ...utils.logging import get_logger
from ..database import Database

logger = get_logger(__name__)

CHANNEL_TYPES = frozenset({"discord", "email", "telegram", "sms", "wechat"})


def new_channel_id() -> str:
    return new_id("ch")


class ChannelConnectionCreate(BaseModel):
    agent_id: str
    user_id: str
    channel_type: str
    name: str = ""
    config: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True


class ChannelConnectionUpdate(BaseModel):
    name: str | None = None
    config: dict[str, Any] | None = None
    is_active: bool | None = None


class ChannelConnection(BaseModel):
    id: str
    agent_id: str
    user_id: str
    channel_type: str
    name: str
    config: dict[str, Any]
    is_active: bool
    created_at: str
    updated_at: str


class ChannelConnectionRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def create(self, data: ChannelConnectionCreate) -> ChannelConnection:
        conn_id = new_channel_id()
        now = datetime.now(timezone.utc).isoformat()
        config_json = json.dumps(data.config)

        await self.db.execute(
            """INSERT INTO channel_connections (
                id, agent_id, user_id, channel_type, name, config, is_active, created_at, updated_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)""",
            (
                conn_id, data.agent_id, data.user_id, data.channel_type,
                data.name, config_json, data.is_active, now, now,
            ),
        )
        await self.db.commit()

        return ChannelConnection(
            id=conn_id,
            agent_id=data.agent_id,
            user_id=data.user_id,
            channel_type=data.channel_type,
            name=data.name,
            config=data.config,
            is_active=data.is_active,
            created_at=now,
            updated_at=now,
        )

    async def get(self, connection_id: str) -> ChannelConnection | None:
        row = await self.db.fetchone(
            "SELECT * FROM channel_connections WHERE id = $1", (connection_id,)
        )
        return self._row_to_model(row) if row else None

    async def list_by_agent(self, agent_id: str) -> list[ChannelConnection]:
        rows = await self.db.fetchall(
            "SELECT * FROM channel_connections WHERE agent_id = $1 ORDER BY created_at ASC",
            (agent_id,),
        )
        return [self._row_to_model(r) for r in rows]

    async def list_active(self) -> list[ChannelConnection]:
        """Return all active connections across all agents — used at startup."""
        rows = await self.db.fetchall(
            "SELECT * FROM channel_connections WHERE is_active = $1 ORDER BY created_at ASC",
            (True,),
        )
        return [self._row_to_model(r) for r in rows]

    async def update(
        self, connection_id: str, data: ChannelConnectionUpdate
    ) -> ChannelConnection | None:
        existing = await self.get(connection_id)
        if existing is None:
            return None

        now = datetime.now(timezone.utc).isoformat()
        updates: dict[str, Any] = {"updated_at": now}

        if data.name is not None:
            updates["name"] = data.name
        if data.config is not None:
            updates["config"] = json.dumps(data.config)
        if data.is_active is not None:
            updates["is_active"] = data.is_active

        parts = []
        values: list[Any] = []
        for i, (k, v) in enumerate(updates.items(), 1):
            parts.append(f"{k} = ${i}")
            values.append(v)
        values.append(connection_id)

        await self.db.execute(
            f"UPDATE channel_connections SET {', '.join(parts)} WHERE id = ${len(values)}",
            tuple(values),
        )
        await self.db.commit()
        return await self.get(connection_id)

    async def delete(self, connection_id: str) -> bool:
        existing = await self.get(connection_id)
        if existing is None:
            return False
        await self.db.execute(
            "DELETE FROM channel_connections WHERE id = $1", (connection_id,)
        )
        await self.db.commit()
        return True

    def _row_to_model(self, row: Any) -> ChannelConnection:
        config: dict[str, Any] = {}
        raw = row["config"]
        if isinstance(raw, str):
            try:
                config = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                pass
        elif isinstance(raw, dict):
            config = raw

        return ChannelConnection(
            id=row["id"],
            agent_id=row["agent_id"],
            user_id=row["user_id"],
            channel_type=row["channel_type"],
            name=row["name"] or "",
            config=config,
            is_active=bool(row["is_active"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )
