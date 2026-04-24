"""ChromaDB-backed memory/RAG store."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel

from ..utils.ids import new_memory_id
from ..utils.logging import get_logger
from .embeddings import get_embedding_function

logger = get_logger(__name__)


class MemorySearchResult(BaseModel):
    id: str
    content: str
    distance: float
    metadata: dict[str, Any] = {}


class MemoryStore:
    """Semantic memory store backed by ChromaDB."""

    def __init__(
        self,
        chroma_path: str = "data/chroma",
        collection_name: str = "aegis_memory",
        embedding_model: str = "all-MiniLM-L6-v2",
    ) -> None:
        self._chroma_path = chroma_path
        self._collection_name = collection_name
        self._embedding_model = embedding_model
        self._client: Any = None
        self._collection: Any = None

    async def initialize(self) -> None:
        """Initialize ChromaDB client and collection."""
        try:
            import chromadb
            from pathlib import Path
            Path(self._chroma_path).mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(path=self._chroma_path)
            ef = get_embedding_function(self._embedding_model)
            kwargs: dict[str, Any] = {"name": self._collection_name}
            if ef is not None:
                kwargs["embedding_function"] = ef
            self._collection = self._client.get_or_create_collection(**kwargs)
            logger.info("Memory store initialized", collection=self._collection_name)
        except ImportError:
            logger.warning("ChromaDB not installed, memory disabled")
        except Exception as e:
            logger.error("Failed to initialize memory store", error=str(e))

    @property
    def available(self) -> bool:
        return self._collection is not None

    async def add(
        self,
        content: str,
        metadata: dict[str, Any] | None = None,
        doc_id: str | None = None,
    ) -> str:
        """Add a document to memory."""
        if not self.available:
            return ""
        mem_id = doc_id or new_memory_id()
        meta = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            **(metadata or {}),
        }
        try:
            self._collection.add(
                documents=[content],
                metadatas=[meta],
                ids=[mem_id],
            )
            return mem_id
        except Exception as e:
            logger.error("Failed to add to memory", error=str(e))
            return ""

    async def search(
        self,
        query: str,
        n_results: int = 5,
        where: dict[str, Any] | None = None,
        min_relevance: float = 0.0,
    ) -> list[MemorySearchResult]:
        """Search memory by semantic similarity."""
        if not self.available:
            return []
        try:
            kwargs: dict[str, Any] = {
                "query_texts": [query],
                "n_results": min(n_results, max(1, self._collection.count())),
            }
            if where:
                kwargs["where"] = where
            results = self._collection.query(**kwargs)

            output = []
            if results and results.get("ids"):
                ids = results["ids"][0]
                docs = results["documents"][0]
                distances = results["distances"][0]
                metas = results.get("metadatas", [[]])[0]
                for i, doc_id in enumerate(ids):
                    distance = distances[i] if distances else 1.0
                    # ChromaDB cosine distance: lower = more similar (0=identical, 2=opposite)
                    # Convert to relevance score [0,1]
                    relevance = 1.0 - (distance / 2.0)
                    if relevance >= min_relevance:
                        output.append(MemorySearchResult(
                            id=doc_id,
                            content=docs[i],
                            distance=distance,
                            metadata=metas[i] if metas else {},
                        ))
            return output
        except Exception as e:
            logger.error("Memory search failed", error=str(e))
            return []

    async def add_message(
        self,
        conversation_id: str,
        message_id: str,
        role: str,
        content: str,
    ) -> str:
        """Add a conversation message to memory."""
        if not content.strip():
            return ""
        return await self.add(
            content=content,
            metadata={
                "conversation_id": conversation_id,
                "message_id": message_id,
                "role": role,
                "type": "message",
            },
        )

    async def get_relevant_context(
        self,
        query: str,
        conversation_id: str | None = None,
        n_results: int = 5,
        min_relevance: float = 0.3,
    ) -> str:
        """Get relevant context as a formatted string for injection."""
        where = None
        if conversation_id:
            # Exclude current conversation to get cross-conversation context
            pass  # ChromaDB where filter is complex; search all for now

        results = await self.search(
            query=query,
            n_results=n_results,
            min_relevance=min_relevance,
        )

        if not results:
            return ""

        # Filter out current conversation messages
        if conversation_id:
            results = [r for r in results if r.metadata.get("conversation_id") != conversation_id]

        if not results:
            return ""

        parts = ["## Relevant Memory Context\n"]
        for r in results:
            role = r.metadata.get("role", "unknown")
            conv_id = r.metadata.get("conversation_id", "")
            parts.append(f"[{role}] (conv: {conv_id[:12]}...): {r.content[:500]}")
        return "\n".join(parts)

    async def delete_by_conversation(self, conversation_id: str) -> None:
        """Delete all memory entries for a conversation."""
        if not self.available:
            return
        try:
            self._collection.delete(where={"conversation_id": conversation_id})
        except Exception as e:
            logger.error("Failed to delete memory entries", error=str(e))

    async def count(self) -> int:
        """Return total number of stored documents."""
        if not self.available:
            return 0
        try:
            return self._collection.count()
        except Exception:
            return 0
