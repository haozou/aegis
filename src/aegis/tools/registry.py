"""Tool registry."""

from __future__ import annotations

import json
from typing import Any

from ..llm.types import ToolDefinition
from ..utils.logging import get_logger
from .base import BaseTool
from .types import ToolContext, ToolResult

logger = get_logger(__name__)


class ToolRegistry:
    """Registry for all available tools."""

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool
        logger.debug("Registered tool", name=tool.name)

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def list_tools(self) -> list[str]:
        return list(self._tools.keys())

    def get_definitions(self, tool_names: list[str] | None = None) -> list[ToolDefinition]:
        """Get LLM tool definitions, optionally filtered by name."""
        tools = list(self._tools.values())
        if tool_names is not None:
            tools = [t for t in tools if t.name in tool_names]
        return [t.to_llm_definition() for t in tools]

    async def execute(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        context: ToolContext,
    ) -> ToolResult:
        """Execute a tool by name."""
        tool = self._tools.get(tool_name)
        if tool is None:
            return ToolResult(output=f"Error: unknown tool '{tool_name}'", is_error=True)

        logger.info("Executing tool", name=tool_name, input_keys=list(tool_input.keys()))
        try:
            result = await tool.execute(context, **tool_input)
            logger.info("Tool completed", name=tool_name, is_error=result.is_error)
            return result
        except Exception as e:
            logger.error("Tool execution exception", name=tool_name, error=str(e))
            return ToolResult(output=f"Tool error: {e}", is_error=True)

    def register_builtins(
        self,
        bash_enabled: bool = True,
        web_fetch_enabled: bool = True,
        web_search_enabled: bool = True,
        file_ops_enabled: bool = True,
        schedule_enabled: bool = True,
        video_enabled: bool = True,
        image_gen_enabled: bool = True,
        document_export_enabled: bool = True,
        python_interpreter_enabled: bool = True,
    ) -> None:
        """Register all built-in tools."""
        if bash_enabled:
            from .bash import BashTool
            self.register(BashTool())

        if web_fetch_enabled:
            from .web_fetch import WebFetchTool
            self.register(WebFetchTool())

        if web_search_enabled:
            from .web_search import WebSearchTool
            self.register(WebSearchTool())

        if file_ops_enabled:
            from .file_ops import FileListTool, FileReadTool, FileWriteTool
            self.register(FileReadTool())
            self.register(FileWriteTool())
            self.register(FileListTool())

        if schedule_enabled:
            from .schedule import ScheduleTool
            self.register(ScheduleTool())

        if video_enabled:
            from .video import (
                VideoAddAudio,
                VideoConcat,
                VideoCut,
                VideoExport,
                VideoOverlayText,
                VideoProbe,
                VideoSpeed,
                VideoThumbnail,
            )
            self.register(VideoProbe())
            self.register(VideoCut())
            self.register(VideoConcat())
            self.register(VideoAddAudio())
            self.register(VideoThumbnail())
            self.register(VideoExport())
            self.register(VideoOverlayText())
            self.register(VideoSpeed())

        if image_gen_enabled:
            from .image_gen import ImageGenerateTool
            self.register(ImageGenerateTool())

        if document_export_enabled:
            from .document_export import FileExportTool
            self.register(FileExportTool())

        if python_interpreter_enabled:
            from .python_interpreter import PythonInterpreterTool
            self.register(PythonInterpreterTool())

        # Knowledge base tool
        from .knowledge import KnowledgeTool
        self.register(KnowledgeTool())

        # Agent delegation tool
        from .agent_delegate import AgentDelegateTool
        self.register(AgentDelegateTool())
