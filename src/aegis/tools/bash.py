"""Bash execution tool."""

from __future__ import annotations

import asyncio
from typing import Any

from ..utils.errors import ToolTimeoutError
from ..utils.logging import get_logger
from .base import BaseTool
from .types import ToolContext, ToolResult

logger = get_logger(__name__)

MAX_OUTPUT_BYTES = 51200  # 50KB


class BashTool(BaseTool):
    """Execute bash commands in a subprocess."""

    @property
    def name(self) -> str:
        return "bash"

    @property
    def description(self) -> str:
        return (
            "Execute a bash shell command and return the output. "
            "Use for running scripts, checking system info, file operations, etc. "
            "Commands run in a sandboxed environment."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The bash command to execute",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds (default: 30, max: 600)",
                    "default": 30,
                },
            },
            "required": ["command"],
        }

    async def execute(self, context: ToolContext, **kwargs: Any) -> ToolResult:
        command = kwargs.get("command", "")
        timeout = min(int(kwargs.get("timeout", context.timeout)), 600)

        if not command.strip():
            return ToolResult(output="Error: empty command", is_error=True)

        logger.debug("Executing bash command", command=command[:100])

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=context.sandbox_path if context.sandbox_path else None,
            )
            try:
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.communicate()
                raise ToolTimeoutError(f"Command timed out after {timeout}s")

            output = stdout.decode("utf-8", errors="replace")
            # Truncate if too long
            if len(output.encode()) > MAX_OUTPUT_BYTES:
                output = output[:MAX_OUTPUT_BYTES // 4]  # rough char limit
                output += f"\n... [output truncated at {MAX_OUTPUT_BYTES // 1024}KB]"

            return_code = proc.returncode or 0
            is_error = return_code != 0
            if is_error:
                output = f"Exit code: {return_code}\n{output}"

            return ToolResult(
                output=output or "(no output)",
                is_error=is_error,
                metadata={"return_code": return_code, "command": command},
            )

        except ToolTimeoutError:
            raise
        except Exception as e:
            logger.error("Bash execution failed", error=str(e))
            return ToolResult(output=f"Error executing command: {e}", is_error=True)
