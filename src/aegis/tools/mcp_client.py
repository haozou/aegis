"""MCP (Model Context Protocol) client.

Supports two transports:
- stdio: Subprocess with JSON-RPC over stdin/stdout
- http: HTTP+SSE with JSON-RPC over HTTP POST / Server-Sent Events
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from abc import ABC, abstractmethod
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import Any

import httpx

from ..utils.logging import get_logger

logger = get_logger(__name__)

# Pattern for detecting device code login messages
# e.g. "To sign in, use a web browser to open https://microsoft.com/devicelogin and enter the code ABCDEF123"
DEVICE_CODE_PATTERN = re.compile(
    r'(https?://[^\s"\'<>]*devicelogin[^\s"\'<>]*)',
    re.IGNORECASE,
)

# Pattern to extract the user code from the message
USER_CODE_PATTERN = re.compile(
    r'(?:code|Code)[:\s]+([A-Z0-9]{6,12})',
)

# Generic auth URL patterns (login pages, OAuth authorize, etc.)
AUTH_URL_PATTERN = re.compile(
    r'(https?://[^\s"\'<>]+(?:'
    r'login\.microsoftonline\.com|'
    r'github\.com/login|'
    r'accounts\.google\.com|'
    r'devicelogin|'
    r'authorize\?|'
    r'device/code'
    r')[^\s"\'<>]*)',
    re.IGNORECASE,
)

# Type for auth callback: (server_id, message) -> None
# message is a user-friendly string like "Visit https://... and enter code ABCDEF"
AuthUrlCallback = Callable[[str, str], Coroutine[Any, Any, None]]


@dataclass
class MCPToolDef:
    """Tool definition from an MCP server."""
    name: str
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)


class BaseMCPTransport(ABC):
    """Abstract transport for MCP communication."""

    @abstractmethod
    async def start(self) -> None: ...

    @abstractmethod
    async def stop(self) -> None: ...

    @abstractmethod
    async def send_request(self, method: str, params: dict[str, Any], request_id: int) -> dict[str, Any] | None: ...

    @abstractmethod
    async def send_notification(self, method: str, params: dict[str, Any]) -> None: ...

    @property
    @abstractmethod
    def is_running(self) -> bool: ...


class StdioTransport(BaseMCPTransport):
    """MCP transport via subprocess stdin/stdout."""

    def __init__(self, command: str, args: list[str], env: dict[str, str]) -> None:
        self._command = command
        self._args = args
        self._env = env
        self._process: asyncio.subprocess.Process | None = None
        self._lock = asyncio.Lock()
        self._stderr_task: asyncio.Task[None] | None = None
        self._on_auth_url: AuthUrlCallback | None = None
        self._server_id: str = ""

    def set_auth_url_callback(self, server_id: str, callback: AuthUrlCallback) -> None:
        """Set callback to invoke when an auth URL is detected in stderr."""
        self._server_id = server_id
        self._on_auth_url = callback

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.returncode is None

    async def start(self) -> None:
        proc_env = dict(os.environ)
        proc_env.update(self._env)

        # Create a fake browser script that prints the URL to stderr
        # instead of opening a real browser. This lets us capture auth URLs
        # from MCP servers that use `open(url)` for OAuth.
        browser_script = f"/tmp/mcp_browser_{id(self)}_{os.getpid()}.sh"
        try:
            with open(browser_script, "w") as f:
                f.write('#!/bin/sh\n')
                f.write('echo "AEGIS_AUTH_URL: $1" >&2\n')
                # Keep the script running briefly so `open` doesn't report failure
                f.write('sleep 1\n')
            os.chmod(browser_script, 0o755)
            proc_env["BROWSER"] = browser_script
            self._browser_script = browser_script
        except Exception:
            proc_env["BROWSER"] = "/usr/bin/false"
            self._browser_script = None

        # Prevent X11/GUI attempts
        proc_env["DISPLAY"] = ""

        try:
            self._process = await asyncio.create_subprocess_exec(
                self._command, *self._args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=proc_env,
                limit=10 * 1024 * 1024,  # 10MB buffer for large tool lists
            )
        except FileNotFoundError:
            raise RuntimeError(f"MCP command not found: {self._command}")
        except Exception as e:
            raise RuntimeError(f"Failed to start MCP process: {e}")

        # Start background task to read stderr for auth messages
        self._stderr_task = asyncio.create_task(self._read_stderr())

    async def stop(self) -> None:
        if self._stderr_task and not self._stderr_task.done():
            self._stderr_task.cancel()
            try:
                await self._stderr_task
            except asyncio.CancelledError:
                pass
            self._stderr_task = None

        if self._process:
            try:
                if self._process.stdin:
                    self._process.stdin.close()
                self._process.terminate()
                try:
                    await asyncio.wait_for(self._process.wait(), timeout=5)
                except asyncio.TimeoutError:
                    self._process.kill()
            except ProcessLookupError:
                pass
            self._process = None

        # Cleanup browser script
        if getattr(self, '_browser_script', None):
            try:
                os.unlink(self._browser_script)
            except OSError:
                pass

    async def _read_stderr(self) -> None:
        """Background task: read stderr and detect auth/device-code messages."""
        if not self._process or not self._process.stderr:
            return

        try:
            while True:
                line = await self._process.stderr.readline()
                if not line:
                    break
                text = line.decode(errors="replace").strip()
                if not text:
                    continue

                logger.info("MCP stderr", server_id=self._server_id, line=text[:300])

                # Check for device code or auth messages
                if self._on_auth_url:
                    auth_message = self._extract_auth_message(text)
                    if auth_message:
                        logger.info("MCP auth message detected", server_id=self._server_id, message=auth_message[:200])
                        try:
                            await self._on_auth_url(self._server_id, auth_message)
                        except Exception as e:
                            logger.warning("Auth callback failed", error=str(e))
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.debug("MCP stderr reader ended", server_id=self._server_id, error=str(e))

    @staticmethod
    def _extract_auth_message(text: str) -> str | None:
        """Extract a device code or auth message from stderr line.

        Returns the full stderr line if it contains auth-related content,
        so the user sees the complete instruction (URL + code).
        """
        lower = text.lower()
        # Our fake browser script prefix
        if text.startswith("AEGIS_AUTH_URL:"):
            url = text.split("AEGIS_AUTH_URL:", 1)[1].strip()
            return f"Sign in required. Open this URL in your browser: {url}"
        # Device code flow: "To sign in, visit https://microsoft.com/devicelogin and enter code XXXXXX"
        if 'devicelogin' in lower or 'device code' in lower or 'device_code' in lower:
            return text
        # Generic: "enter the code" / "enter code" with a URL
        if ('enter' in lower and 'code' in lower) or ('sign in' in lower and 'http' in lower):
            return text
        # Auth URL detected (login pages)
        if AUTH_URL_PATTERN.search(text):
            return text
        return None

    async def send_request(self, method: str, params: dict[str, Any], request_id: int) -> dict[str, Any] | None:
        async with self._lock:
            if not self._process or not self._process.stdin or not self._process.stdout:
                return None

            request = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
            try:
                self._process.stdin.write(json.dumps(request).encode() + b"\n")
                await self._process.stdin.drain()

                while True:
                    line = await asyncio.wait_for(self._process.stdout.readline(), timeout=120)
                    if not line:
                        return None
                    line_str = line.decode().strip()
                    if not line_str:
                        continue
                    try:
                        response = json.loads(line_str)
                    except json.JSONDecodeError:
                        continue
                    if "id" not in response:
                        continue  # Skip notifications
                    if response.get("id") == request_id:
                        if "error" in response:
                            logger.error("MCP stdio error", method=method, error=response["error"])
                            return None
                        return response.get("result", {})
            except asyncio.TimeoutError:
                logger.error("MCP stdio timeout", method=method)
                return None
            except Exception as e:
                logger.error("MCP stdio failed", method=method, error=str(e))
                return None

    async def send_notification(self, method: str, params: dict[str, Any]) -> None:
        if not self._process or not self._process.stdin:
            return
        notification = {"jsonrpc": "2.0", "method": method, "params": params}
        try:
            self._process.stdin.write(json.dumps(notification).encode() + b"\n")
            await self._process.stdin.drain()
        except Exception:
            pass


class HttpTransport(BaseMCPTransport):
    """MCP transport via HTTP POST (Streamable HTTP or legacy SSE)."""

    def __init__(self, url: str, headers: dict[str, str] | None = None) -> None:
        self._url = url.rstrip("/")
        self._headers = headers or {}
        self._client: httpx.AsyncClient | None = None
        self._session_url: str | None = None
        self._running = False
        self._oauth_token: str | None = None

    def set_oauth_token(self, token: str) -> None:
        """Set the OAuth bearer token for authenticated requests."""
        self._oauth_token = token

    @property
    def is_running(self) -> bool:
        return self._running

    async def start(self) -> None:
        auth_headers = {**self._headers}
        if self._oauth_token:
            auth_headers["Authorization"] = f"Bearer {self._oauth_token}"

        self._client = httpx.AsyncClient(
            timeout=60,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                **auth_headers,
            },
            follow_redirects=True,
        )
        self._running = True

    async def stop(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
        self._running = False

    async def send_request(self, method: str, params: dict[str, Any], request_id: int) -> dict[str, Any] | None:
        if not self._client:
            return None

        request = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
        target_url = self._session_url or self._url

        try:
            resp = await self._client.post(target_url, json=request)

            # Check for session URL in response header
            if "mcp-session-id" in resp.headers:
                session_id = resp.headers["mcp-session-id"]
                self._session_url = f"{self._url}?sessionId={session_id}"

            content_type = resp.headers.get("content-type", "")

            if "text/event-stream" in content_type:
                # SSE response — parse events
                return self._parse_sse_response(resp.text, request_id)
            else:
                # Direct JSON response
                data = resp.json()
                if isinstance(data, dict):
                    if "error" in data:
                        logger.error("MCP HTTP error", method=method, error=data["error"])
                        return None
                    return data.get("result", {})
                # Could be a batch response
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and item.get("id") == request_id:
                            if "error" in item:
                                return None
                            return item.get("result", {})
                return None

        except Exception as e:
            logger.error("MCP HTTP request failed", method=method, url=target_url, error=str(e))
            return None

    def _parse_sse_response(self, text: str, request_id: int) -> dict[str, Any] | None:
        """Parse Server-Sent Events response to extract JSON-RPC result."""
        for line in text.split("\n"):
            line = line.strip()
            if line.startswith("data:"):
                data_str = line[5:].strip()
                if not data_str:
                    continue
                try:
                    data = json.loads(data_str)
                    if isinstance(data, dict) and data.get("id") == request_id:
                        if "error" in data:
                            return None
                        return data.get("result", {})
                except json.JSONDecodeError:
                    continue
        return None

    async def send_notification(self, method: str, params: dict[str, Any]) -> None:
        if not self._client:
            return
        notification = {"jsonrpc": "2.0", "method": method, "params": params}
        target_url = self._session_url or self._url
        try:
            await self._client.post(target_url, json=notification)
        except Exception:
            pass


class MCPClient:
    """High-level MCP client that works with any transport."""

    def __init__(self, server_id: str, transport: BaseMCPTransport) -> None:
        self.server_id = server_id
        self._transport = transport
        self._request_id = 0
        self._started = False

    @property
    def is_running(self) -> bool:
        return self._started and self._transport.is_running

    async def start(self) -> None:
        if self._started:
            return

        logger.info("Starting MCP server", server_id=self.server_id)
        await self._transport.start()

        # Initialize
        init_result = await self._send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "aegis", "version": "0.1.0"},
        })

        if init_result is None:
            await self._transport.stop()
            raise RuntimeError(f"MCP server '{self.server_id}' did not respond to initialize")

        await self._transport.send_notification("notifications/initialized", {})
        self._started = True

        logger.info(
            "MCP server started",
            server_id=self.server_id,
            server_info=init_result.get("serverInfo", {}),
        )

    async def stop(self) -> None:
        await self._transport.stop()
        self._started = False
        logger.info("MCP server stopped", server_id=self.server_id)

    async def list_tools(self) -> list[MCPToolDef]:
        result = await self._send_request("tools/list", {})
        if result is None:
            return []

        tools = []
        for t in result.get("tools", []):
            tools.append(MCPToolDef(
                name=t.get("name", ""),
                description=t.get("description", ""),
                input_schema=t.get("inputSchema", {}),
            ))

        logger.info("MCP tools discovered", server_id=self.server_id,
                     tool_count=len(tools), tool_names=[t.name for t in tools])
        return tools

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> str:
        result = await self._send_request("tools/call", {
            "name": tool_name,
            "arguments": arguments,
        })

        if result is None:
            return "Error: MCP server did not respond"

        content = result.get("content", [])
        if isinstance(content, list):
            texts = []
            for item in content:
                if isinstance(item, dict):
                    if item.get("type") == "text":
                        texts.append(item.get("text", ""))
                    else:
                        texts.append(json.dumps(item, indent=2))
                else:
                    texts.append(str(item))
            return "\n".join(texts) if texts else json.dumps(result)

        return json.dumps(result)

    async def _send_request(self, method: str, params: dict[str, Any]) -> dict[str, Any] | None:
        self._request_id += 1
        return await self._transport.send_request(method, params, self._request_id)


def create_mcp_client(
    server_id: str,
    command: str = "",
    args: list[str] | None = None,
    env: dict[str, str] | None = None,
    url: str = "",
    headers: dict[str, str] | None = None,
    transport_type: str = "",
    oauth_token: str = "",
    on_auth_url: AuthUrlCallback | None = None,
) -> MCPClient:
    """Factory to create an MCPClient with the right transport.

    Auto-detects transport type:
    - If `url` is provided → HTTP transport
    - If `command` is provided → stdio transport
    - `transport_type` can override: "stdio", "http", "sse"
    """
    if transport_type in ("http", "sse") or (url and not command):
        if not url:
            raise ValueError(f"MCP server '{server_id}': HTTP transport requires a URL")
        transport = HttpTransport(url=url, headers=headers)
        if oauth_token:
            transport.set_oauth_token(oauth_token)
    elif transport_type == "stdio" or (command and not url):
        if not command:
            raise ValueError(f"MCP server '{server_id}': stdio transport requires a command")
        transport = StdioTransport(command=command, args=args or [], env=env or {})
        if on_auth_url:
            transport.set_auth_url_callback(server_id, on_auth_url)
    elif url:
        transport = HttpTransport(url=url, headers=headers)
        if oauth_token:
            transport.set_oauth_token(oauth_token)
    elif command:
        transport = StdioTransport(command=command, args=args or [], env=env or {})
        if on_auth_url:
            transport.set_auth_url_callback(server_id, on_auth_url)
    else:
        raise ValueError(f"MCP server '{server_id}': provide either 'command' (stdio) or 'url' (http)")

    return MCPClient(server_id=server_id, transport=transport)


async def discover_oauth_metadata(mcp_url: str) -> dict[str, Any] | None:
    """Discover OAuth 2.0 metadata from an MCP server.

    Per MCP spec, the server exposes OAuth metadata at:
    - {origin}/.well-known/oauth-authorization-server

    Returns the metadata dict or None if not available.
    """
    from urllib.parse import urlparse

    parsed = urlparse(mcp_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    metadata_url = f"{origin}/.well-known/oauth-authorization-server"

    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            resp = await client.get(metadata_url)
            if resp.status_code == 200:
                return resp.json()
    except Exception as e:
        logger.debug("OAuth discovery failed", url=metadata_url, error=str(e))

    return None


async def exchange_oauth_code(
    token_endpoint: str,
    code: str,
    client_id: str,
    redirect_uri: str,
    code_verifier: str = "",
) -> dict[str, Any] | None:
    """Exchange an OAuth authorization code for an access token."""
    data: dict[str, str] = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": client_id,
        "redirect_uri": redirect_uri,
    }
    if code_verifier:
        data["code_verifier"] = code_verifier

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(token_endpoint, data=data)
            if resp.status_code == 200:
                return resp.json()
            logger.error("OAuth token exchange failed", status=resp.status_code, body=resp.text[:200])
    except Exception as e:
        logger.error("OAuth token exchange error", error=str(e))

    return None
