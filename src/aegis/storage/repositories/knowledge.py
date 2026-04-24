"""Knowledge document repository."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from ..database import Database
from ...utils.ids import new_id


class KnowledgeDoc(BaseModel):
    id: str
    agent_id: str
    user_id: str
    name: str = ""
    source_type: str = "text"  # text, url, file
    source_url: str | None = None
    content_hash: str | None = None
    content: str | None = None
    chunk_count: int = 0
    status: str = "pending"  # pending, processing, ready, error
    error: str | None = None
    metadata: dict[str, Any] = {}
    created_at: datetime | None = None


class KnowledgeDocCreate(BaseModel):
    agent_id: str
    user_id: str
    name: str = ""
    source_type: str = "text"
    source_url: str | None = None
    content_hash: str | None = None


class KnowledgeDocRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def _row_to_model(self, row: dict[str, Any]) -> KnowledgeDoc:
        metadata = row.get("metadata", "{}")
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        return KnowledgeDoc(
            id=row["id"],
            agent_id=row["agent_id"],
            user_id=row["user_id"],
            name=row.get("name", ""),
            source_type=row.get("source_type", "text"),
            source_url=row.get("source_url"),
            content_hash=row.get("content_hash"),
            content=row.get("content"),
            chunk_count=row.get("chunk_count", 0),
            status=row.get("status", "pending"),
            error=row.get("error"),
            metadata=metadata,
            created_at=row.get("created_at"),
        )

    async def create(self, data: KnowledgeDocCreate) -> KnowledgeDoc:
        doc_id = new_id("kb")
        await self.db.execute(
            "INSERT INTO knowledge_documents (id, agent_id, user_id, name, source_type, source_url, content_hash) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7)",
            (doc_id, data.agent_id, data.user_id, data.name, data.source_type,
             data.source_url, data.content_hash),
        )
        row = await self.db.fetchone("SELECT * FROM knowledge_documents WHERE id = $1", (doc_id,))
        return self._row_to_model(row)

    async def get(self, doc_id: str) -> KnowledgeDoc | None:
        row = await self.db.fetchone("SELECT * FROM knowledge_documents WHERE id = $1", (doc_id,))
        return self._row_to_model(row) if row else None

    async def list_by_agent(self, agent_id: str) -> list[KnowledgeDoc]:
        rows = await self.db.fetchall(
            "SELECT * FROM knowledge_documents WHERE agent_id = $1 ORDER BY created_at DESC",
            (agent_id,),
        )
        return [self._row_to_model(r) for r in rows]

    async def update_status(self, doc_id: str, status: str, chunk_count: int = 0, error: str | None = None) -> None:
        await self.db.execute(
            "UPDATE knowledge_documents SET status = $1, chunk_count = $2, error = $3 WHERE id = $4",
            (status, chunk_count, error, doc_id),
        )

    async def delete(self, doc_id: str) -> None:
        await self.db.execute("DELETE FROM knowledge_documents WHERE id = $1", (doc_id,))

    async def update_name(self, doc_id: str, name: str) -> None:
        await self.db.execute(
            "UPDATE knowledge_documents SET name = $1 WHERE id = $2",
            (name, doc_id),
        )

    async def update_content(self, doc_id: str, content: str) -> None:
        await self.db.execute(
            "UPDATE knowledge_documents SET content = $1 WHERE id = $2",
            (content, doc_id),
        )
