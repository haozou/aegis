"""File operation tools."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from ..utils.logging import get_logger
from .base import BaseTool
from .types import ToolContext, ToolResult

logger = get_logger(__name__)

MAX_FILE_SIZE = 1024 * 1024  # 1MB


def _resolve_safe_path(path_str: str, context: ToolContext) -> Path | None:
    """Resolve path and verify it's within allowed directories."""
    target = Path(path_str).expanduser().resolve()

    allowed = []
    for p in context.allowed_paths:
        allowed.append(Path(p).expanduser().resolve())
    if context.sandbox_path:
        allowed.append(Path(context.sandbox_path).expanduser().resolve())

    if not allowed:
        return target  # No restrictions

    for allowed_path in allowed:
        try:
            target.relative_to(allowed_path)
            return target
        except ValueError:
            continue

    return None


class FileReadTool(BaseTool):
    """Read file contents."""

    @property
    def name(self) -> str:
        return "file_read"

    @property
    def description(self) -> str:
        return "Read the contents of a file. Returns the file content as text."

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to the file to read"},
                "encoding": {"type": "string", "description": "File encoding (default: utf-8)", "default": "utf-8"},
            },
            "required": ["path"],
        }

    async def execute(self, context: ToolContext, **kwargs: Any) -> ToolResult:
        path_str = kwargs.get("path", "")
        encoding = kwargs.get("encoding", "utf-8")

        if not path_str:
            return ToolResult(output="Error: path required", is_error=True)

        safe_path = _resolve_safe_path(path_str, context)
        if safe_path is None:
            return ToolResult(output=f"Error: path '{path_str}' is outside allowed directories", is_error=True)

        try:
            if not safe_path.exists():
                return ToolResult(output=f"Error: file '{path_str}' does not exist", is_error=True)
            if safe_path.stat().st_size > MAX_FILE_SIZE:
                return ToolResult(output="Error: file exceeds 1MB size limit", is_error=True)
            content = safe_path.read_text(encoding=encoding, errors="replace")
            return ToolResult(output=content, metadata={"path": str(safe_path), "size": len(content)})
        except Exception as e:
            return ToolResult(output=f"Error reading file: {e}", is_error=True)


class FileWriteTool(BaseTool):
    """Write content to a file."""

    @property
    def name(self) -> str:
        return "file_write"

    @property
    def description(self) -> str:
        return "Write content to a file. Creates parent directories if needed."

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to write the file"},
                "content": {"type": "string", "description": "Content to write"},
                "append": {"type": "boolean", "description": "Append instead of overwrite", "default": False},
            },
            "required": ["path", "content"],
        }

    async def execute(self, context: ToolContext, **kwargs: Any) -> ToolResult:
        path_str = kwargs.get("path", "")
        content = kwargs.get("content", "")
        append = bool(kwargs.get("append", False))

        if not path_str:
            return ToolResult(output="Error: path required", is_error=True)

        safe_path = _resolve_safe_path(path_str, context)
        if safe_path is None:
            return ToolResult(output=f"Error: path '{path_str}' is outside allowed directories", is_error=True)

        try:
            safe_path.parent.mkdir(parents=True, exist_ok=True)
            if not append:
                safe_path.write_text(content, encoding="utf-8")
            else:
                with safe_path.open("a", encoding="utf-8") as fh:
                    fh.write(content)
            return ToolResult(
                output=f"Successfully {'appended to' if append else 'wrote'} '{path_str}' ({len(content)} chars)",
                metadata={"path": str(safe_path), "chars_written": len(content)},
            )
        except Exception as e:
            return ToolResult(output=f"Error writing file: {e}", is_error=True)


class FileListTool(BaseTool):
    """List files in a directory."""

    @property
    def name(self) -> str:
        return "file_list"

    @property
    def description(self) -> str:
        return "List files and directories at a given path. Returns a tree-like listing."

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory path to list (default: sandbox)", "default": "."},
                "pattern": {"type": "string", "description": "Glob pattern filter (e.g., '*.py')", "default": "*"},
                "recursive": {"type": "boolean", "description": "List recursively", "default": False},
            },
        }

    async def execute(self, context: ToolContext, **kwargs: Any) -> ToolResult:
        path_str = kwargs.get("path", context.sandbox_path or ".")
        pattern = kwargs.get("pattern", "*")
        recursive = bool(kwargs.get("recursive", False))

        safe_path = _resolve_safe_path(path_str, context)
        if safe_path is None:
            return ToolResult(output=f"Error: path '{path_str}' is outside allowed directories", is_error=True)

        try:
            if not safe_path.exists():
                return ToolResult(output=f"Error: path '{path_str}' does not exist", is_error=True)
            if not safe_path.is_dir():
                return ToolResult(output=f"Error: '{path_str}' is not a directory", is_error=True)

            if recursive:
                entries = list(safe_path.rglob(pattern))
            else:
                entries = list(safe_path.glob(pattern))

            entries.sort(key=lambda p: (p.is_file(), str(p)))
            lines = [f"Contents of {safe_path}:"]
            for entry in entries[:200]:  # Limit output
                rel = entry.relative_to(safe_path)
                prefix = "  " if entry.is_file() else "📁 "
                size_str = f" ({entry.stat().st_size:,} bytes)" if entry.is_file() else "/"
                lines.append(f"  {prefix}{rel}{size_str}")

            if len(entries) > 200:
                lines.append(f"  ... and {len(entries) - 200} more entries")

            return ToolResult(output="\n".join(lines))
        except Exception as e:
            return ToolResult(output=f"Error listing directory: {e}", is_error=True)
