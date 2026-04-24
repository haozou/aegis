"""Tool type definitions."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ToolResult(BaseModel):
    """Result from tool execution."""
    output: str
    is_error: bool = False
    metadata: dict[str, Any] = {}


class ToolContext(BaseModel):
    """Context passed to tool execution."""
    model_config = {"arbitrary_types_allowed": True}

    session_id: str = ""
    conversation_id: str = ""
    agent_id: str = ""
    user_id: str = ""
    allowed_paths: list[str] = []
    sandbox_path: str = "data/sandbox"
    timeout: int = 120
    # Optional: repository access for tools that manage platform resources
    repositories: Any = None
    # Optional: memory store for knowledge base / RAG
    memory_store: Any = None
