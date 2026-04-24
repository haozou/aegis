"""Agent repository."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from ...utils.ids import new_agent_id
from ...utils.logging import get_logger
from ..database import Database

logger = get_logger(__name__)


class AgentCreate(BaseModel):
    user_id: str
    name: str
    slug: str
    description: str = ""
    provider: str = "anthropic"
    model: str = "claude-sonnet-4-5"
    temperature: float = 0.7
    max_tokens: int = 4096
    system_prompt: str = ""
    enable_memory: bool = False
    enable_skills: bool = False
    max_tool_iterations: int = 10
    allowed_tools: list[str] = Field(
        default_factory=lambda: ["web_fetch", "file_read", "file_write", "file_list"]
    )


class AgentUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    status: str | None = None
    avatar_url: str | None = None
    provider: str | None = None
    model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    system_prompt: str | None = None
    enable_memory: bool | None = None
    enable_skills: bool | None = None
    max_tool_iterations: int | None = None
    allowed_tools: list[str] | None = None
    metadata: dict[str, Any] | None = None


class Agent(BaseModel):
    id: str
    user_id: str
    slug: str
    name: str
    description: str = ""
    avatar_url: str | None = None
    status: str = "active"
    is_public: bool = False
    created_at: str
    updated_at: str
    provider: str = "anthropic"
    model: str = "claude-sonnet-4-5"
    temperature: float = 0.7
    max_tokens: int = 4096
    system_prompt: str = ""
    enable_memory: bool = False
    enable_skills: bool = False
    max_tool_iterations: int = 10
    allowed_tools: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def create(self, data: AgentCreate) -> Agent:
        agent_id = new_agent_id()
        now = datetime.now(timezone.utc).isoformat()
        allowed_tools_json = json.dumps(data.allowed_tools)

        await self.db.execute(
            """INSERT INTO agents (
                id, user_id, slug, name, description, created_at, updated_at,
                provider, model, temperature, max_tokens, system_prompt,
                enable_memory, enable_skills, max_tool_iterations, allowed_tools
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)""",
            (
                agent_id, data.user_id, data.slug, data.name, data.description,
                now, now, data.provider, data.model, data.temperature,
                data.max_tokens, data.system_prompt,
                data.enable_memory, data.enable_skills,
                data.max_tool_iterations, allowed_tools_json,
            ),
        )
        await self.db.commit()

        return Agent(
            id=agent_id, user_id=data.user_id, slug=data.slug, name=data.name,
            description=data.description, created_at=now, updated_at=now,
            provider=data.provider, model=data.model, temperature=data.temperature,
            max_tokens=data.max_tokens, system_prompt=data.system_prompt,
            enable_memory=data.enable_memory, enable_skills=data.enable_skills,
            max_tool_iterations=data.max_tool_iterations,
            allowed_tools=data.allowed_tools,
        )

    async def get(self, agent_id: str) -> Agent | None:
        row = await self.db.fetchone("SELECT * FROM agents WHERE id = $1", (agent_id,))
        if row is None:
            return None
        return self._row_to_model(row)

    async def get_by_slug(self, user_id: str, slug: str) -> Agent | None:
        row = await self.db.fetchone(
            "SELECT * FROM agents WHERE user_id = $1 AND slug = $2", (user_id, slug),
        )
        if row is None:
            return None
        return self._row_to_model(row)

    async def list_by_user(
        self, user_id: str, status: str | None = None,
        limit: int = 100, offset: int = 0,
    ) -> list[Agent]:
        if status:
            rows = await self.db.fetchall(
                "SELECT * FROM agents WHERE user_id = $1 AND status = $2 ORDER BY updated_at DESC LIMIT $3 OFFSET $4",
                (user_id, status, limit, offset),
            )
        else:
            rows = await self.db.fetchall(
                "SELECT * FROM agents WHERE user_id = $1 ORDER BY updated_at DESC LIMIT $2 OFFSET $3",
                (user_id, limit, offset),
            )
        return [self._row_to_model(r) for r in rows]

    async def update(self, agent_id: str, data: AgentUpdate) -> Agent | None:
        existing = await self.get(agent_id)
        if existing is None:
            return None

        now = datetime.now(timezone.utc).isoformat()
        updates: dict[str, Any] = {"updated_at": now}

        for field_name in (
            "name", "description", "status", "avatar_url",
            "provider", "model", "temperature", "max_tokens",
            "system_prompt", "max_tool_iterations",
        ):
            val = getattr(data, field_name, None)
            if val is not None:
                updates[field_name] = val

        if data.enable_memory is not None:
            updates["enable_memory"] = data.enable_memory
        if data.enable_skills is not None:
            updates["enable_skills"] = data.enable_skills
        if data.allowed_tools is not None:
            updates["allowed_tools"] = json.dumps(data.allowed_tools)
        if data.metadata is not None:
            updates["metadata"] = json.dumps(data.metadata)

        parts = []
        values: list[Any] = []
        for i, (k, v) in enumerate(updates.items(), 1):
            parts.append(f"{k} = ${i}")
            values.append(v)
        values.append(agent_id)
        set_clause = ", ".join(parts)
        await self.db.execute(
            f"UPDATE agents SET {set_clause} WHERE id = ${len(values)}", tuple(values)
        )
        await self.db.commit()
        return await self.get(agent_id)

    async def delete(self, agent_id: str) -> bool:
        existing = await self.get(agent_id)
        if existing is None:
            return False
        await self.db.execute("DELETE FROM agents WHERE id = $1", (agent_id,))
        await self.db.commit()
        return True

    def _row_to_model(self, row: Any) -> Agent:
        allowed_tools: list[str] = []
        raw = row["allowed_tools"]
        if isinstance(raw, str):
            try:
                allowed_tools = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                pass
        elif isinstance(raw, list):
            allowed_tools = raw

        metadata: dict[str, Any] = {}
        raw_meta = row["metadata"]
        if isinstance(raw_meta, str):
            try:
                metadata = json.loads(raw_meta)
            except (json.JSONDecodeError, TypeError):
                pass
        elif isinstance(raw_meta, dict):
            metadata = raw_meta

        return Agent(
            id=row["id"],
            user_id=row["user_id"],
            slug=row["slug"],
            name=row["name"],
            description=row["description"],
            avatar_url=row["avatar_url"],
            status=row["status"],
            is_public=bool(row["is_public"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            provider=row["provider"],
            model=row["model"],
            temperature=row["temperature"],
            max_tokens=row["max_tokens"],
            system_prompt=row["system_prompt"],
            enable_memory=bool(row["enable_memory"]),
            enable_skills=bool(row["enable_skills"]),
            max_tool_iterations=row["max_tool_iterations"],
            allowed_tools=allowed_tools,
            metadata=metadata,
        )
