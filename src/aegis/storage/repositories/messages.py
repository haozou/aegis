"""Message repository."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from ...utils.ids import new_message_id
from ...utils.logging import get_logger
from ..database import Database

logger = get_logger(__name__)


class ContentPart(BaseModel):
    type: str
    text: str | None = None
    id: str | None = None
    name: str | None = None
    input: dict[str, Any] | None = None
    content: Any = None
    is_error: bool | None = None


class ToolCall(BaseModel):
    id: str
    name: str
    input: dict[str, Any] = Field(default_factory=dict)
    output: str | None = None
    is_error: bool = False


class MessageCreate(BaseModel):
    conversation_id: str
    role: str
    content: list[ContentPart] | str
    tool_calls: list[ToolCall] | None = None
    tool_call_id: str | None = None
    tokens_used: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class Message(BaseModel):
    id: str
    conversation_id: str
    role: str
    content: list[ContentPart] | str
    tool_calls: list[ToolCall] | None = None
    tool_call_id: str | None = None
    created_at: str
    tokens_used: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)

    def get_text_content(self) -> str:
        if isinstance(self.content, str):
            return self.content
        parts = []
        for part in self.content:
            if part.type == "text" and part.text:
                parts.append(part.text)
        return "\n".join(parts)


class MessageRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def create(self, data: MessageCreate) -> Message:
        msg_id = new_message_id()
        now = datetime.now(timezone.utc).isoformat()

        content_json = (
            json.dumps([p.model_dump(exclude_none=True) for p in data.content])
            if isinstance(data.content, list)
            else json.dumps(data.content)
        )
        tool_calls_json = (
            json.dumps([tc.model_dump(exclude_none=True) for tc in data.tool_calls])
            if data.tool_calls
            else None
        )

        await self.db.execute(
            """INSERT INTO messages (id, conversation_id, role, content, tool_calls, tool_call_id, created_at, tokens_used, metadata)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)""",
            (msg_id, data.conversation_id, data.role, content_json,
             tool_calls_json, data.tool_call_id, now, data.tokens_used,
             json.dumps(data.metadata)),
        )
        await self.db.commit()
        return Message(
            id=msg_id, conversation_id=data.conversation_id, role=data.role,
            content=data.content, tool_calls=data.tool_calls,
            tool_call_id=data.tool_call_id, created_at=now,
            tokens_used=data.tokens_used, metadata=data.metadata,
        )

    async def get_by_conversation(self, conversation_id: str) -> list[Message]:
        rows = await self.db.fetchall(
            "SELECT * FROM messages WHERE conversation_id = $1 ORDER BY created_at ASC",
            (conversation_id,),
        )
        return [self._row_to_model(r) for r in rows]

    async def get(self, message_id: str) -> Message | None:
        row = await self.db.fetchone("SELECT * FROM messages WHERE id = $1", (message_id,))
        return self._row_to_model(row) if row else None

    async def delete_from(self, conversation_id: str, after_created_at: str) -> None:
        """Delete all messages in a conversation created after the given timestamp."""
        await self.db.execute(
            "DELETE FROM messages WHERE conversation_id = $1 AND created_at > $2",
            (conversation_id, after_created_at),
        )
        await self.db.commit()

    async def delete_after_last_user_message(self, conversation_id: str) -> None:
        """Delete all messages after (but not including) the last user message."""
        rows = await self.db.fetchall(
            "SELECT id, created_at FROM messages WHERE conversation_id = $1 AND role = 'user' ORDER BY created_at DESC LIMIT 1",
            (conversation_id,),
        )
        if not rows:
            return
        last_user_ts = rows[0]["created_at"]
        await self.db.execute(
            "DELETE FROM messages WHERE conversation_id = $1 AND created_at > $2",
            (conversation_id, last_user_ts),
        )
        await self.db.commit()

    def _row_to_model(self, row: Any) -> Message:
        content_raw = row["content"]
        try:
            content_parsed = json.loads(content_raw) if isinstance(content_raw, str) else content_raw
            if isinstance(content_parsed, list):
                parts: list[ContentPart] = []
                for p in content_parsed:
                    if isinstance(p, dict) and "type" in p:
                        try:
                            parts.append(ContentPart(**p))
                        except Exception:
                            parts.append(ContentPart(type="text", text=json.dumps(p)))
                    elif isinstance(p, dict):
                        # Dict without 'type' — wrap as text
                        parts.append(ContentPart(type="text", text=json.dumps(p)))
                    elif isinstance(p, str):
                        parts.append(ContentPart(type="text", text=p))
                content: list[ContentPart] | str = parts
            else:
                content = str(content_parsed)
        except (json.JSONDecodeError, TypeError):
            content = str(content_raw)

        tool_calls = None
        tc_raw = row["tool_calls"]
        if tc_raw:
            try:
                tc_list = json.loads(tc_raw) if isinstance(tc_raw, str) else tc_raw
                tool_calls = [ToolCall(**tc) for tc in tc_list]
            except (json.JSONDecodeError, TypeError):
                pass

        metadata = row["metadata"]
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except (json.JSONDecodeError, TypeError):
                metadata = {}

        return Message(
            id=row["id"],
            conversation_id=row["conversation_id"],
            role=row["role"],
            content=content,
            tool_calls=tool_calls,
            tool_call_id=row["tool_call_id"],
            created_at=str(row["created_at"]),
            tokens_used=row["tokens_used"] or 0,
            metadata=metadata or {},
        )
