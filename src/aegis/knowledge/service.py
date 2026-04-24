"""Knowledge base service — manages document ingestion, chunking, and RAG search."""

from __future__ import annotations

import hashlib
from typing import Any

from ..memory.store import MemoryStore
from ..utils.logging import get_logger

logger = get_logger(__name__)


def chunk_text(text: str, chunk_size: int = 1000, overlap: int = 200) -> list[str]:
    """Split text into overlapping chunks."""
    if len(text) <= chunk_size:
        return [text] if text.strip() else []
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start += chunk_size - overlap
    return chunks


class KnowledgeService:
    """Manages per-agent knowledge bases using ChromaDB."""

    def __init__(self, memory_store: MemoryStore) -> None:
        self._memory = memory_store

    def _collection_name(self, agent_id: str) -> str:
        return f"kb_{agent_id}"

    def _get_collection(self, agent_id: str) -> Any:
        """Get or create a ChromaDB collection for an agent's knowledge base."""
        if not self._memory._client:
            return None
        try:
            from ..memory.embeddings import get_embedding_function
            ef = get_embedding_function(self._memory._embedding_model)
            kwargs: dict[str, Any] = {"name": self._collection_name(agent_id)}
            if ef is not None:
                kwargs["embedding_function"] = ef
            return self._memory._client.get_or_create_collection(**kwargs)
        except Exception as e:
            logger.error("Failed to get KB collection", agent_id=agent_id, error=str(e))
            return None

    async def add_text(
        self,
        agent_id: str,
        doc_id: str,
        text: str,
        source_name: str = "",
        source_url: str = "",
    ) -> int:
        """Chunk and embed text into the agent's knowledge base. Returns chunk count."""
        collection = self._get_collection(agent_id)
        if not collection:
            raise RuntimeError("Knowledge base not available (ChromaDB not initialized)")

        chunks = chunk_text(text)
        if not chunks:
            return 0

        ids = [f"{doc_id}_chunk_{i}" for i in range(len(chunks))]
        metadatas = [{
            "doc_id": doc_id,
            "chunk_index": i,
            "source_name": source_name,
            "source_url": source_url,
        } for i in range(len(chunks))]

        try:
            collection.add(documents=chunks, metadatas=metadatas, ids=ids)
            logger.info("Knowledge added", agent_id=agent_id, doc_id=doc_id, chunks=len(chunks))
            return len(chunks)
        except Exception as e:
            logger.error("Failed to add knowledge", error=str(e))
            raise

    async def add_url(
        self,
        agent_id: str,
        doc_id: str,
        url: str,
    ) -> tuple[str, int, str]:
        """Fetch a URL, extract text, chunk and embed. Returns (text_preview, chunk_count, full_text)."""
        import httpx
        import html2text

        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(url, headers={
                "User-Agent": "Mozilla/5.0 (compatible; Aegis/1.0)",
            })
            resp.raise_for_status()

        content_type = resp.headers.get("content-type", "")
        if "html" in content_type:
            h = html2text.HTML2Text()
            h.ignore_links = False
            h.ignore_images = True
            text = h.handle(resp.text)
        else:
            text = resp.text

        chunk_count = await self.add_text(agent_id, doc_id, text, source_url=url)
        preview = text[:200] + "..." if len(text) > 200 else text
        return preview, chunk_count, text

    async def search(
        self,
        agent_id: str,
        query: str,
        n_results: int = 5,
    ) -> list[dict[str, Any]]:
        """Search the agent's knowledge base. Returns list of {content, source_name, source_url, relevance}."""
        collection = self._get_collection(agent_id)
        if not collection or collection.count() == 0:
            return []

        try:
            results = collection.query(
                query_texts=[query],
                n_results=min(n_results, collection.count()),
            )
        except Exception as e:
            logger.error("Knowledge search failed", error=str(e))
            return []

        output = []
        if results and results.get("ids"):
            ids = results["ids"][0]
            docs = results["documents"][0]
            distances = results["distances"][0]
            metas = results.get("metadatas", [[]])[0]
            for i in range(len(ids)):
                relevance = 1.0 - (distances[i] / 2.0) if distances else 0.5
                output.append({
                    "content": docs[i],
                    "source_name": metas[i].get("source_name", "") if metas else "",
                    "source_url": metas[i].get("source_url", "") if metas else "",
                    "doc_id": metas[i].get("doc_id", "") if metas else "",
                    "relevance": round(relevance, 3),
                })
        return output

    async def delete_document(self, agent_id: str, doc_id: str) -> None:
        """Remove all chunks for a document from the knowledge base."""
        collection = self._get_collection(agent_id)
        if not collection:
            return
        try:
            collection.delete(where={"doc_id": doc_id})
            logger.info("Knowledge document deleted", agent_id=agent_id, doc_id=doc_id)
        except Exception as e:
            logger.error("Failed to delete knowledge", error=str(e))

    async def get_context(self, agent_id: str, query: str, n_results: int = 5) -> str:
        """Get relevant knowledge as formatted context for LLM injection."""
        results = await self.search(agent_id, query, n_results)
        if not results:
            return ""

        parts = ["## Relevant Knowledge\n"]
        for r in results:
            source = r.get("source_name") or r.get("source_url") or "unknown"
            parts.append(f"[Source: {source}] {r['content'][:500]}")
        return "\n\n".join(parts)

    @staticmethod
    def content_hash(text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()[:16]
