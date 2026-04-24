"""Base tool interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..llm.types import ToolDefinition
from .types import ToolContext, ToolResult


class BaseTool(ABC):
    """Abstract base for all tools."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Tool name (used in LLM tool calls)."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Tool description for the LLM."""
        ...

    @property
    @abstractmethod
    def parameters_schema(self) -> dict[str, Any]:
        """JSON Schema for tool parameters."""
        ...

    @abstractmethod
    async def execute(self, context: ToolContext, **kwargs: Any) -> ToolResult:
        """Execute the tool with given parameters."""
        ...

    def to_llm_definition(self) -> ToolDefinition:
        """Convert to LLM tool definition."""
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters=self.parameters_schema,
        )
