"""Knowledge base tool — lets the agent search and manage its knowledge base."""

from __future__ import annotations

import json
from typing import Any

from ..utils.logging import get_logger
from .base import BaseTool
from .types import ToolContext, ToolResult

logger = get_logger(__name__)


class KnowledgeTool(BaseTool):
    """Search, add URLs/text, list, and delete from the agent's knowledge base."""

    @property
    def name(self) -> str:
        return "knowledge_base"

    @property
    def description(self) -> str:
        return (
            "Manage the agent's knowledge base. You can search for relevant information, "
            "add URLs or text to learn from, list existing documents, or delete them. "
            "Use 'search' to find information before answering questions about specific topics. "
            "Use 'add_url' when the user asks you to learn from a webpage."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["search", "add_url", "add_text", "list", "delete"],
                    "description": "Action: search knowledge, add a URL, add text, list documents, or delete a document.",
                },
                "query": {
                    "type": "string",
                    "description": "Search query (for 'search' action).",
                },
                "url": {
                    "type": "string",
                    "description": "URL to fetch and add to knowledge base (for 'add_url' action).",
                },
                "text": {
                    "type": "string",
                    "description": "Text content to add to knowledge base (for 'add_text' action).",
                },
                "name": {
                    "type": "string",
                    "description": "Name/title for the document being added.",
                },
                "document_id": {
                    "type": "string",
                    "description": "Document ID to delete (for 'delete' action).",
                },
            },
            "required": ["action"],
        }

    async def execute(self, context: ToolContext, **kwargs: Any) -> ToolResult:
        action = kwargs.get("action", "")
        repos = context.repositories
        if not repos or not context.agent_id:
            return ToolResult(output="Error: No context available.", is_error=True)

        # Get knowledge service — either from attached _kb_service or create from memory_store
        kb_service = getattr(context, '_kb_service', None)
        if not kb_service and context.memory_store and context.memory_store.available:
            try:
                from ..knowledge.service import KnowledgeService
                kb_service = KnowledgeService(context.memory_store)
            except Exception:
                pass

        if not kb_service:
            return ToolResult(output="Knowledge base service not available. ChromaDB may not be initialized.", is_error=True)

        try:
            if action == "search":
                return await self._search(kb_service, context, **kwargs)
            elif action == "add_url":
                return await self._add_url(kb_service, repos, context, **kwargs)
            elif action == "add_text":
                return await self._add_text(kb_service, repos, context, **kwargs)
            elif action == "list":
                return await self._list(repos, context)
            elif action == "delete":
                return await self._delete(kb_service, repos, context, **kwargs)
            else:
                return ToolResult(output=f"Unknown action: {action}", is_error=True)
        except Exception as e:
            logger.error("Knowledge tool error", action=action, error=str(e))
            return ToolResult(output=f"Error: {e}", is_error=True)

    async def _search(self, kb_service: Any, context: ToolContext, **kwargs: Any) -> ToolResult:
        query = kwargs.get("query", "")
        if not query:
            return ToolResult(output="Error: query is required for search.", is_error=True)
        results = await kb_service.search(context.agent_id, query)
        if not results:
            return ToolResult(output="No relevant knowledge found.")
        return ToolResult(output=json.dumps(results, indent=2))

    async def _add_url(self, kb_service: Any, repos: Any, context: ToolContext, **kwargs: Any) -> ToolResult:
        from ..storage.repositories.knowledge import KnowledgeDocCreate
        url = kwargs.get("url", "")
        name = kwargs.get("name", url)
        if not url:
            return ToolResult(output="Error: url is required.", is_error=True)

        doc = await repos.knowledge.create(KnowledgeDocCreate(
            agent_id=context.agent_id, user_id=context.user_id,
            name=name, source_type="url", source_url=url,
        ))
        await repos.knowledge.update_status(doc.id, "processing")
        try:
            preview, chunk_count, fetched_text = await kb_service.add_url(context.agent_id, doc.id, url)
            await repos.knowledge.update_content(doc.id, fetched_text)
            await repos.knowledge.update_status(doc.id, "ready", chunk_count=chunk_count)
            return ToolResult(output=json.dumps({
                "status": "added", "document_id": doc.id, "name": name,
                "chunks": chunk_count, "preview": preview,
            }, indent=2))
        except Exception as e:
            await repos.knowledge.update_status(doc.id, "error", error=str(e))
            return ToolResult(output=f"Failed to add URL: {e}", is_error=True)

    async def _add_text(self, kb_service: Any, repos: Any, context: ToolContext, **kwargs: Any) -> ToolResult:
        from ..storage.repositories.knowledge import KnowledgeDocCreate
        text = kwargs.get("text", "")
        name = kwargs.get("name", "Text snippet")
        if not text:
            return ToolResult(output="Error: text is required.", is_error=True)

        doc = await repos.knowledge.create(KnowledgeDocCreate(
            agent_id=context.agent_id, user_id=context.user_id,
            name=name, source_type="text",
            content_hash=kb_service.content_hash(text),
        ))
        chunk_count = await kb_service.add_text(context.agent_id, doc.id, text, source_name=name)
        await repos.knowledge.update_content(doc.id, text)
        await repos.knowledge.update_status(doc.id, "ready", chunk_count=chunk_count)
        return ToolResult(output=json.dumps({
            "status": "added", "document_id": doc.id, "name": name, "chunks": chunk_count,
        }))

    async def _list(self, repos: Any, context: ToolContext) -> ToolResult:
        docs = await repos.knowledge.list_by_agent(context.agent_id)
        if not docs:
            return ToolResult(output="No documents in knowledge base.")
        return ToolResult(output=json.dumps([{
            "id": d.id, "name": d.name, "source_type": d.source_type,
            "source_url": d.source_url, "status": d.status,
            "chunks": d.chunk_count,
        } for d in docs], indent=2))

    async def _delete(self, kb_service: Any, repos: Any, context: ToolContext, **kwargs: Any) -> ToolResult:
        doc_id = kwargs.get("document_id", "")
        if not doc_id:
            return ToolResult(output="Error: document_id is required.", is_error=True)
        doc = await repos.knowledge.get(doc_id)
        if not doc or doc.agent_id != context.agent_id:
            return ToolResult(output="Document not found.", is_error=True)
        await kb_service.delete_document(context.agent_id, doc_id)
        await repos.knowledge.delete(doc_id)
        return ToolResult(output=json.dumps({"status": "deleted", "document_id": doc_id, "name": doc.name}))
