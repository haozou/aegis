"""MCP tool wrapper — adapts MCP tools to the BaseTool interface."""

from __future__ import annotations

from typing import Any

from ..utils.logging import get_logger
from .base import BaseTool
from .mcp_client import MCPClient, MCPToolDef, create_mcp_client, AuthUrlCallback
from .types import ToolContext, ToolResult

logger = get_logger(__name__)


class MCPTool(BaseTool):
    """Wraps a single MCP tool as a BaseTool for the tool registry."""

    def __init__(self, server_id: str, tool_def: MCPToolDef, client: MCPClient) -> None:
        self._server_id = server_id
        self._tool_def = tool_def
        self._client = client

    @property
    def name(self) -> str:
        return f"mcp__{self._server_id}__{self._tool_def.name}"

    @property
    def description(self) -> str:
        return self._tool_def.description or f"MCP tool from {self._server_id}"

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return self._tool_def.input_schema or {"type": "object", "properties": {}}

    async def execute(self, context: ToolContext, **kwargs: Any) -> ToolResult:
        """Execute the MCP tool by forwarding to the MCP server."""
        if not self._client.is_running:
            # Try to detect why it's not running
            transport = self._client._transport
            if hasattr(transport, '_process') and transport._process:
                rc = transport._process.returncode
                return ToolResult(
                    output=f"Error: MCP server '{self._server_id}' has stopped (exit code: {rc}). "
                           f"The server may need to be restarted. Try starting a new chat.",
                    is_error=True,
                )
            return ToolResult(
                output=f"Error: MCP server '{self._server_id}' is not running",
                is_error=True,
            )

        logger.info(
            "Calling MCP tool",
            server_id=self._server_id,
            tool=self._tool_def.name,
            input_keys=list(kwargs.keys()),
        )

        try:
            import asyncio
            result = await asyncio.wait_for(
                self._client.call_tool(self._tool_def.name, kwargs),
                timeout=context.timeout,
            )
            return ToolResult(output=result)
        except asyncio.TimeoutError:
            # Check if process died during the call
            alive = self._client.is_running
            return ToolResult(
                output=f"MCP tool '{self._tool_def.name}' timed out after {context.timeout}s. "
                       f"Server still alive: {alive}. "
                       f"This may be caused by expired Azure CLI credentials — try running 'az login' in the container.",
                is_error=True,
            )
        except Exception as e:
            logger.error(
                "MCP tool execution failed",
                server_id=self._server_id,
                tool=self._tool_def.name,
                error=str(e),
            )
            return ToolResult(output=f"MCP tool error: {e}", is_error=True)


async def start_mcp_servers(
    mcp_configs: list[dict[str, Any]],
    tool_registry: Any,
    on_auth_url: AuthUrlCallback | None = None,
) -> list[MCPClient]:
    """Start MCP servers from config and register their tools.

    Args:
        mcp_configs: List of MCP server configurations.
        tool_registry: ToolRegistry to register discovered tools.
        on_auth_url: Optional callback invoked when an MCP server needs
                     browser-based auth. Receives (server_id, auth_url).

    Returns the list of started clients (caller must stop them later).
    """
    clients: list[MCPClient] = []

    for config in mcp_configs:
        if not config.get("enabled", True):
            continue

        server_id = config.get("id", "")
        command = config.get("command", "")
        url = config.get("url", "")
        if not server_id or (not command and not url):
            continue

        try:
            client = create_mcp_client(
                server_id=server_id,
                command=command,
                args=config.get("args", []),
                env=config.get("env", {}),
                url=url,
                headers=config.get("headers", {}),
                transport_type=config.get("transport", ""),
                oauth_token=config.get("oauth_token", ""),
                on_auth_url=on_auth_url,
            )
        except ValueError as e:
            logger.error("Invalid MCP config", server_id=server_id, error=str(e))
            continue

        try:
            await client.start()
            tools = await client.list_tools()

            # Filter tools if enabled_tools is specified
            enabled_tools = config.get("enabled_tools", [])
            if enabled_tools:
                tools = [t for t in tools if t.name in enabled_tools]

            logger.info("MCP server tools loaded", server_id=server_id,
                        total_discovered=len(await client.list_tools()) if not enabled_tools else "filtered",
                        registered=len(tools))

            for tool_def in tools:
                mcp_tool = MCPTool(server_id, tool_def, client)
                tool_registry.register(mcp_tool)

            clients.append(client)
            logger.info("MCP server ready", server_id=server_id,
                        tools=[t.name for t in tools])
        except Exception as e:
            logger.error("Failed to start MCP server", server_id=server_id, error=str(e))
            await client.stop()

    return clients


async def stop_mcp_servers(clients: list[MCPClient]) -> None:
    """Stop all MCP server clients."""
    for client in clients:
        try:
            await client.stop()
        except Exception as e:
            logger.warning("Error stopping MCP client", server_id=client.server_id, error=str(e))
