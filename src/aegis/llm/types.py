"""LLM type definitions."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class LLMMessage(BaseModel):
    """A message in an LLM conversation."""
    role: Literal["system", "user", "assistant", "tool"]
    content: Any  # str or list[dict] for multi-part
    tool_call_id: str | None = None
    tool_calls: list[dict[str, Any]] | None = None


class ToolDefinition(BaseModel):
    """Tool definition for LLM tool calling."""
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema


class ToolCallResult(BaseModel):
    """Result from executing a tool call."""
    tool_call_id: str
    tool_name: str
    output: str
    is_error: bool = False


class LLMRequest(BaseModel):
    """Request to an LLM provider."""
    messages: list[LLMMessage]
    model: str
    system_prompt: str | None = None
    tools: list[ToolDefinition] = Field(default_factory=list)
    temperature: float = 0.7
    max_tokens: int = 4096
    stream: bool = False


class ToolCallDelta(BaseModel):
    """Incremental tool call in a stream."""
    index: int = 0
    id: str | None = None
    name: str | None = None
    input_json: str = ""  # accumulates


class StreamDelta(BaseModel):
    """A single chunk from a streaming response."""
    text: str | None = None
    tool_call_id: str | None = None
    tool_name: str | None = None
    tool_input: dict[str, Any] | None = None
    is_tool_start: bool = False
    is_done: bool = False
    input_tokens: int = 0
    output_tokens: int = 0


class LLMResponse(BaseModel):
    """Complete response from an LLM provider."""
    content: str = ""
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""
    stop_reason: str = "end_turn"
