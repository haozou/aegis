"""Core agent type definitions."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class StreamEventType(str, Enum):
    SESSION_READY = "session_ready"
    TEXT_DELTA = "text_delta"
    TOOL_START = "tool_start"
    TOOL_RESULT = "tool_result"
    DONE = "done"
    ERROR = "error"
    CANCELLED = "cancelled"


class StreamEvent(BaseModel):
    """An event emitted during agent streaming."""
    type: StreamEventType
    # TEXT_DELTA
    text: str | None = None
    # TOOL_START
    tool_name: str | None = None
    tool_id: str | None = None
    tool_input: dict[str, Any] | None = None
    # TOOL_RESULT
    tool_output: str | None = None
    is_error: bool | None = None
    # DONE
    message_id: str | None = None
    usage: dict[str, int] | None = None
    # ERROR
    error: str | None = None

    def to_ws_dict(self) -> dict[str, Any]:
        """Serialize for WebSocket transmission."""
        d: dict[str, Any] = {"type": self.type.value}
        for field in ("text", "tool_name", "tool_id", "tool_input",
                      "tool_output", "is_error", "message_id", "usage", "error"):
            val = getattr(self, field, None)
            if val is not None:
                d[field] = val
        return d


class AgentConfig(BaseModel):
    """Configuration for an agent run."""
    provider: str = ""   # unused for routing — get_provider() picks the active backend
    model: str = "claude-sonnet-4-5"
    temperature: float = 0.7
    max_tokens: int = 4096
    system_prompt: str = ""
    enable_memory: bool = True
    enable_skills: bool = True
    tool_names: list[str] | None = None  # None = all available
    max_tool_iterations: int = 50
    agent_id: str = ""
    user_id: str = ""
    skip_user_message_save: bool = False  # True when resending — message already in DB
