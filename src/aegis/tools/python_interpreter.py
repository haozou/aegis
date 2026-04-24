"""Python Code Interpreter — persistent stateful Python execution with file output."""

from __future__ import annotations

import asyncio
import os
import pathlib
import textwrap
import time
from typing import Any

from ..utils.logging import get_logger
from .base import BaseTool
from .types import ToolContext, ToolResult

logger = get_logger(__name__)

# Sentinel markers for protocol between host and subprocess
_BEGIN = "___AEGIS_BEGIN___"
_END = "___AEGIS_END___"
_FILES_BEGIN = "___AEGIS_FILES___"
_ERROR = "___AEGIS_ERROR___"

# The REPL script that runs inside the subprocess
_REPL_SCRIPT = textwrap.dedent(r'''
import sys, os, io, json, traceback, glob

# Ensure sandbox is the working directory
SANDBOX = os.environ.get("SANDBOX_PATH", "data/sandbox")
os.makedirs(SANDBOX, exist_ok=True)
os.chdir(SANDBOX)

# Patch matplotlib to non-interactive backend and auto-save
try:
    import matplotlib
    matplotlib.use("Agg")
except ImportError:
    pass

BEGIN = "___AEGIS_BEGIN___"
END = "___AEGIS_END___"
FILES_BEGIN = "___AEGIS_FILES___"
ERROR = "___AEGIS_ERROR___"

_user_ns = {"__name__": "__main__", "__builtins__": __builtins__}

def _snapshot_files():
    """Get set of files currently in sandbox."""
    result = set()
    for root, dirs, files in os.walk("."):
        for f in files:
            result.add(os.path.join(root, f))
    return result

while True:
    # Read until we see BEGIN sentinel
    line = ""
    try:
        line = sys.stdin.readline()
    except EOFError:
        break
    if not line:
        break
    line = line.strip()
    if line != BEGIN:
        continue

    # Read code lines until END sentinel
    code_lines = []
    while True:
        cline = sys.stdin.readline()
        if not cline:
            break
        if cline.strip() == END:
            break
        code_lines.append(cline)

    code = "".join(code_lines)

    # Snapshot files before execution
    before_files = _snapshot_files()

    # Capture stdout/stderr
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    buf = io.StringIO()
    sys.stdout = buf
    sys.stderr = buf

    error_occurred = False
    try:
        # Auto-save matplotlib figures
        compiled = compile(code, "<interpreter>", "exec")
        exec(compiled, _user_ns)

        # If matplotlib was used, save any open figures
        try:
            import matplotlib.pyplot as plt
            figs = [plt.figure(n) for n in plt.get_fignums()]
            for i, fig in enumerate(figs):
                fname = f"figure_{len(before_files) + i + 1}.png"
                fig.savefig(fname, dpi=150, bbox_inches="tight")
            if figs:
                plt.close("all")
        except ImportError:
            pass
        except Exception:
            pass

    except Exception:
        error_occurred = True
        traceback.print_exc(file=buf)

    sys.stdout = old_stdout
    sys.stderr = old_stderr

    output = buf.getvalue()

    # Find new files
    after_files = _snapshot_files()
    new_files = sorted(after_files - before_files)

    # Print results with sentinels
    print(BEGIN, flush=True)
    if error_occurred:
        print(ERROR, flush=True)
    print(output, end="", flush=True)
    if new_files:
        print(FILES_BEGIN, flush=True)
        for f in new_files:
            size = os.path.getsize(f)
            print(json.dumps({"path": f, "size": size}), flush=True)
    print(END, flush=True)
''')

# Track active interpreters per conversation
_interpreters: dict[str, dict[str, Any]] = {}
_IDLE_TIMEOUT = 1800  # 30 minutes


class PythonInterpreterTool(BaseTool):
    """Execute Python code with persistent state across calls."""

    @property
    def name(self) -> str:
        return "python"

    @property
    def description(self) -> str:
        return (
            "Execute Python code in a persistent interpreter session. "
            "Variables, imports, and function definitions persist across calls within the same conversation. "
            "Available libraries: pandas, numpy, matplotlib, seaborn, scipy, Pillow, openpyxl, json, csv, etc. "
            "Generated files (plots, CSVs, documents) are automatically detected and returned as download links. "
            "Use matplotlib for charts/plots — figures are auto-saved as PNG. "
            "Working directory is a sandbox — you can read/write files freely."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Python code to execute. Can be multi-line. Variables persist between calls.",
                },
            },
            "required": ["code"],
        }

    async def execute(self, context: ToolContext, **kwargs: Any) -> ToolResult:
        code = kwargs.get("code", "")
        if not code.strip():
            return ToolResult(output="Error: no code provided", is_error=True)

        conv_id = context.conversation_id or "default"
        sandbox = pathlib.Path(context.sandbox_path or "data/sandbox")
        sandbox.mkdir(parents=True, exist_ok=True)

        timeout = min(context.timeout or 120, 600)

        # Get or create interpreter for this conversation
        interp = await self._get_interpreter(conv_id, sandbox)

        try:
            # Send code to interpreter
            interp["process"].stdin.write(f"{_BEGIN}\n".encode())
            interp["process"].stdin.write(code.encode())
            if not code.endswith("\n"):
                interp["process"].stdin.write(b"\n")
            interp["process"].stdin.write(f"{_END}\n".encode())
            await interp["process"].stdin.drain()

            # Read output until we see our sentinels
            output_lines: list[str] = []
            new_files: list[dict] = []
            is_error = False
            in_files = False
            started = False

            async def read_output():
                nonlocal is_error, in_files, started
                while True:
                    raw = await interp["process"].stdout.readline()
                    if not raw:
                        break
                    line = raw.decode("utf-8", errors="replace").rstrip("\n")

                    if line == _BEGIN and not started:
                        started = True
                        continue
                    if line == _END and started:
                        return
                    if line == _ERROR:
                        is_error = True
                        continue
                    if line == _FILES_BEGIN:
                        in_files = True
                        continue

                    if not started:
                        continue

                    if in_files:
                        try:
                            import json
                            new_files.append(json.loads(line))
                        except Exception:
                            pass
                    else:
                        output_lines.append(line)

            await asyncio.wait_for(read_output(), timeout=timeout)
            interp["last_used"] = time.time()

            output_text = "\n".join(output_lines)

            # Truncate if too large
            if len(output_text) > 50000:
                output_text = output_text[:50000] + "\n... (output truncated at 50KB)"

            # List new files (but don't upload — let file_export handle that)
            file_notes: list[str] = []
            for finfo in new_files:
                fname = pathlib.Path(finfo["path"]).name
                size = finfo.get("size", 0)
                file_notes.append(f"  - {fname} ({size:,} bytes)")

            # Build result
            parts = []
            if output_text.strip():
                parts.append(output_text)
            if file_notes:
                parts.append("Files created:\n" + "\n".join(file_notes) + "\n\nUse the file_export tool to make these downloadable.")

            result_text = "\n\n".join(parts) if parts else "(no output)"

            return ToolResult(
                output=result_text,
                is_error=is_error,
                metadata={
                    "files": [f.get("path", "") for f in new_files],
                    "conversation_id": conv_id,
                },
            )

        except asyncio.TimeoutError:
            # Kill the stuck interpreter
            await self._kill_interpreter(conv_id)
            return ToolResult(
                output=f"Execution timed out after {timeout}s. The interpreter has been reset.",
                is_error=True,
            )
        except Exception as e:
            logger.error("Python interpreter error", error=str(e))
            await self._kill_interpreter(conv_id)
            return ToolResult(output=f"Interpreter error: {e}", is_error=True)

    async def _get_interpreter(
        self, conv_id: str, sandbox: pathlib.Path
    ) -> dict[str, Any]:
        """Get or create a persistent Python subprocess for this conversation."""
        # Clean up idle interpreters
        await self._cleanup_idle()

        if conv_id in _interpreters:
            interp = _interpreters[conv_id]
            if interp["process"].returncode is None:
                return interp
            # Process died, remove it
            del _interpreters[conv_id]

        # Start new interpreter
        env = os.environ.copy()
        env["SANDBOX_PATH"] = str(sandbox)
        env["MPLBACKEND"] = "Agg"

        process = await asyncio.create_subprocess_exec(
            "python3", "-u", "-c", _REPL_SCRIPT,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=env,
            cwd=str(sandbox),
        )

        interp = {
            "process": process,
            "last_used": time.time(),
            "sandbox": sandbox,
        }
        _interpreters[conv_id] = interp
        return interp

    async def _kill_interpreter(self, conv_id: str) -> None:
        """Kill and remove an interpreter."""
        interp = _interpreters.pop(conv_id, None)
        if interp and interp["process"].returncode is None:
            try:
                interp["process"].kill()
                await interp["process"].wait()
            except Exception:
                pass

    async def _cleanup_idle(self) -> None:
        """Kill interpreters that have been idle too long."""
        now = time.time()
        to_kill = [
            cid for cid, interp in _interpreters.items()
            if now - interp["last_used"] > _IDLE_TIMEOUT
            or interp["process"].returncode is not None
        ]
        for cid in to_kill:
            await self._kill_interpreter(cid)
