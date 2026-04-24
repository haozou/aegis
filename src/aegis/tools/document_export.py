"""File export tool — make sandbox files downloadable via the file API."""

from __future__ import annotations

import mimetypes
import pathlib
import uuid
from typing import Any

from ..utils.logging import get_logger
from .base import BaseTool
from .types import ToolContext, ToolResult

logger = get_logger(__name__)


class FileExportTool(BaseTool):
    """Export a file from the sandbox as a downloadable link."""

    @property
    def name(self) -> str:
        return "file_export"

    @property
    def description(self) -> str:
        return (
            "Make a file from the working directory available for download. "
            "Use this after creating a file (PDF, DOCX, CSV, image, etc.) with the Python tool "
            "to give the user a download link. "
            "Provide the file path relative to the working directory."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file in the working directory (e.g. 'resume.pdf', 'report.docx', 'chart.png').",
                },
            },
            "required": ["path"],
        }

    async def execute(self, context: ToolContext, **kwargs: Any) -> ToolResult:
        rel_path = kwargs.get("path", "")
        if not rel_path.strip():
            return ToolResult(output="Error: path is required", is_error=True)

        sandbox = pathlib.Path(context.sandbox_path or "data/sandbox")
        file_path = (sandbox / rel_path).resolve()

        # Security: ensure file is within sandbox
        try:
            file_path.relative_to(sandbox.resolve())
        except ValueError:
            return ToolResult(output="Error: path must be within the working directory", is_error=True)

        if not file_path.exists():
            return ToolResult(output=f"Error: file not found: {rel_path}", is_error=True)

        if not file_path.is_file():
            return ToolResult(output=f"Error: not a file: {rel_path}", is_error=True)

        # Upload to file API
        file_id = uuid.uuid4().hex
        filename = file_path.name
        upload_dir = pathlib.Path("data/uploads") / (context.user_id or "system")
        upload_dir.mkdir(parents=True, exist_ok=True)
        dest = upload_dir / f"{file_id}_{filename}"
        dest.write_bytes(file_path.read_bytes())

        file_size = file_path.stat().st_size
        media_type, _ = mimetypes.guess_type(str(file_path))
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

        # Use image markdown for images, download link for everything else
        if ext in ("png", "jpg", "jpeg", "gif", "svg", "webp"):
            link = f"![{filename}](/api/files/{file_id})"
        else:
            link = f"[Download {filename}](/api/files/{file_id})"

        return ToolResult(
            output=f"{link} ({file_size:,} bytes)",
            metadata={
                "file_id": file_id,
                "filename": filename,
                "size": file_size,
                "media_type": media_type or "application/octet-stream",
            },
        )
