"""Agent delegation tool — lets one agent invoke another agent."""

from __future__ import annotations

import json
from typing import Any

from ..utils.logging import get_logger
from .base import BaseTool
from .types import ToolContext, ToolResult

logger = get_logger(__name__)

# Prevent infinite recursion
_DELEGATION_DEPTH = 0
MAX_DELEGATION_DEPTH = 3


class AgentDelegateTool(BaseTool):
    """Delegate a task to another agent owned by the same user."""

    @property
    def name(self) -> str:
        return "delegate_to_agent"

    @property
    def description(self) -> str:
        return (
            "Delegate a task to another agent. Use this when a task is better handled by "
            "a specialized agent (e.g. delegate DevOps questions to a DevOps agent, "
            "or ask a code review agent to review changes). "
            "The other agent will process the message and return its response. "
            "You can only delegate to agents owned by the same user."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "agent_name": {
                    "type": "string",
                    "description": "Name or slug of the agent to delegate to.",
                },
                "message": {
                    "type": "string",
                    "description": "The message/task to send to the other agent.",
                },
            },
            "required": ["agent_name", "message"],
        }

    async def execute(self, context: ToolContext, **kwargs: Any) -> ToolResult:
        global _DELEGATION_DEPTH

        agent_name = kwargs.get("agent_name", "")
        message = kwargs.get("message", "")

        if not agent_name or not message:
            return ToolResult(output="Error: agent_name and message are required.", is_error=True)

        repos = context.repositories
        if not repos or not context.user_id:
            return ToolResult(output="Error: No context available.", is_error=True)

        # Recursion guard
        if _DELEGATION_DEPTH >= MAX_DELEGATION_DEPTH:
            return ToolResult(
                output=f"Error: Maximum delegation depth ({MAX_DELEGATION_DEPTH}) reached. Cannot delegate further.",
                is_error=True,
            )

        try:
            # Find the target agent by name or slug
            agents = await repos.agents.list_by_user(context.user_id)
            target = None
            for a in agents:
                if a.name.lower() == agent_name.lower() or a.slug == agent_name.lower():
                    target = a
                    break

            if not target:
                available = [a.name for a in agents if a.id != context.agent_id and a.status == "active"]
                return ToolResult(
                    output=f"Agent '{agent_name}' not found. Available agents: {', '.join(available) or 'none'}",
                    is_error=True,
                )

            if target.id == context.agent_id:
                return ToolResult(output="Error: Cannot delegate to yourself.", is_error=True)

            if target.status != "active":
                return ToolResult(output=f"Error: Agent '{target.name}' is {target.status}.", is_error=True)

            logger.info("Agent delegation",
                        from_agent=context.agent_id, to_agent=target.id,
                        to_name=target.name, message_preview=message[:100])

            # Create a temporary session for the target agent
            from ..core.orchestrator import AgentOrchestrator
            from ..core.types import AgentConfig, StreamEventType
            from ..storage.repositories.conversations import ConversationCreate
            from ..tools.registry import ToolRegistry
            from ..tools.mcp_tool import start_mcp_servers, stop_mcp_servers

            # Build config for target agent
            config = AgentConfig(
                provider=target.provider, model=target.model,
                temperature=target.temperature, max_tokens=target.max_tokens,
                system_prompt=target.system_prompt,
                tool_names=target.allowed_tools if target.allowed_tools else None,
                max_tool_iterations=target.max_tool_iterations,
                agent_id=target.id, user_id=context.user_id,
            )

            # Build session-scoped registry with MCP
            session_registry = ToolRegistry()
            # Copy built-in tools from the tool context's registry
            # We need to get the base registry - use a fresh one
            session_registry.register_builtins()

            # Start MCP servers for the target agent
            mcp_configs = target.metadata.get("mcp_servers", [])
            mcp_clients = []
            if mcp_configs:
                mcp_clients = await start_mcp_servers(mcp_configs, session_registry)

            # Append MCP tool names
            all_mcp_tools = [t for t in session_registry.list_tools() if t.startswith("mcp__")]
            if config.tool_names is not None and all_mcp_tools:
                config = AgentConfig(
                    **{**config.model_dump(), "tool_names": config.tool_names + all_mcp_tools}
                )

            # Create conversation for the delegation
            source_agent = await repos.agents.get(context.agent_id)
            source_name = source_agent.name if source_agent else "Unknown"
            conv_title = f"📨 From {source_name}: {message[:40]}{'...' if len(message) > 40 else ''}"
            conv = await repos.conversations.create(ConversationCreate(
                title=conv_title,
                provider=target.provider, model=target.model,
                user_id=context.user_id, agent_id=target.id,
            ))

            # Create orchestrator and session
            delegate_orchestrator = AgentOrchestrator(
                db=context.repositories.conversations.db,
                repositories=repos,
                tool_registry=session_registry,
                memory_store=context.memory_store,
            )
            session = delegate_orchestrator.create_session(config=config)

            # Run the agent
            full_text = ""
            _DELEGATION_DEPTH += 1
            try:
                async for event in delegate_orchestrator.send_message(
                    session_id=session.id, conversation_id=conv.id,
                    content=message, config=config,
                ):
                    if event.type == StreamEventType.TEXT_DELTA and event.text:
                        full_text += event.text
                    elif event.type == StreamEventType.ERROR:
                        raise RuntimeError(event.error or "Delegate agent error")
            finally:
                _DELEGATION_DEPTH -= 1
                delegate_orchestrator.close_session(session.id)
                if mcp_clients:
                    await stop_mcp_servers(mcp_clients)

            if not full_text:
                return ToolResult(output=f"Agent '{target.name}' did not produce a response.", is_error=True)

            logger.info("Delegation completed",
                        to_agent=target.name, response_len=len(full_text))

            return ToolResult(output=json.dumps({
                "agent": target.name,
                "agent_id": target.id,
                "conversation_id": conv.id,
                "response": full_text,
            }, indent=2))

        except Exception as e:
            logger.error("Delegation failed", error=str(e))
            return ToolResult(output=f"Delegation failed: {e}", is_error=True)
