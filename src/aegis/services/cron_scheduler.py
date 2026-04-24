"""Cron scheduler — background task that runs due scheduled tasks."""

from __future__ import annotations

import asyncio
from typing import Any

from ..core.types import AgentConfig, StreamEventType
from ..storage.repositories.conversations import ConversationCreate
from ..tools.mcp_tool import start_mcp_servers, stop_mcp_servers
from ..tools.registry import ToolRegistry
from ..utils.logging import get_logger

logger = get_logger(__name__)


def _agent_to_config(agent: Any) -> AgentConfig:
    return AgentConfig(
        provider=agent.provider, model=agent.model,
        temperature=agent.temperature, max_tokens=agent.max_tokens,
        system_prompt=agent.system_prompt,
        enable_memory=agent.enable_memory, enable_skills=agent.enable_skills,
        tool_names=agent.allowed_tools if agent.allowed_tools else None,
        max_tool_iterations=agent.max_tool_iterations,
        agent_id=agent.id,
        user_id=agent.user_id,
    )


class CronScheduler:
    """Background scheduler that checks for due cron tasks and executes them."""

    def __init__(
        self,
        repositories: Any,
        orchestrator: Any,
        tool_registry: Any,
        db: Any = None,
        memory_store: Any | None = None,
        webhook_dispatcher: Any | None = None,
        tick_interval: int = 60,
    ) -> None:
        self._repos = repositories
        self._orchestrator = orchestrator
        self._base_registry = tool_registry
        self._db = db
        self._memory_store = memory_store
        self._webhook_dispatcher = webhook_dispatcher
        self._tick_interval = tick_interval
        self._running = False
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Start the scheduler background loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("Cron scheduler started", interval=self._tick_interval)

    async def stop(self) -> None:
        """Stop the scheduler."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("Cron scheduler stopped")

    async def _loop(self) -> None:
        """Main scheduler loop."""
        while self._running:
            try:
                await self._tick()
            except Exception as e:
                logger.error("Cron tick error", error=str(e))

            await asyncio.sleep(self._tick_interval)

    async def _tick(self) -> None:
        """Check for due tasks and execute them."""
        due_tasks = await self._repos.scheduled_tasks.get_due()
        if not due_tasks:
            return

        logger.info("Cron tick: found due tasks", count=len(due_tasks))

        for task in due_tasks:
            asyncio.create_task(self._execute_task(task))

    async def _execute_task(self, task: Any) -> None:
        """Execute a single scheduled task with MCP support."""
        logger.info("Executing scheduled task", task_id=task.id, name=task.name)

        run = await self._repos.scheduled_tasks.log_run(task.id, status="running")
        mcp_clients: list[Any] = []

        try:
            agent = await self._repos.agents.get(task.agent_id)
            if not agent or agent.status != "active":
                await self._repos.scheduled_tasks.complete_run(
                    run.id, status="failed", error="Agent not active",
                )
                await self._repos.scheduled_tasks.mark_run(task.id)
                return

            conv = await self._repos.conversations.create(ConversationCreate(
                title=f"Cron: {task.name or task.cron_expr}",
                provider=agent.provider, model=agent.model,
                user_id=task.user_id, agent_id=agent.id,
            ))

            await self._repos.scheduled_tasks.complete_run(run.id, status="running")

            # Build session-scoped tool registry with MCP tools
            session_registry = ToolRegistry()
            for tool_name in self._base_registry.list_tools():
                tool = self._base_registry.get(tool_name)
                if tool:
                    session_registry.register(tool)

            # Start MCP servers if configured
            mcp_configs = agent.metadata.get("mcp_servers", [])
            if mcp_configs:
                logger.info("Starting MCP servers for cron task",
                            task_id=task.id, count=len(mcp_configs))
                mcp_clients = await start_mcp_servers(mcp_configs, session_registry)

            # Build config with MCP tools included
            config = _agent_to_config(agent)
            all_mcp_tools = [t for t in session_registry.list_tools() if t.startswith("mcp__")]
            if config.tool_names is not None and all_mcp_tools:
                config = AgentConfig(
                    **{**config.model_dump(), "tool_names": config.tool_names + all_mcp_tools}
                )

            # Create orchestrator with session-scoped registry
            from ..core.orchestrator import AgentOrchestrator
            session_orchestrator = AgentOrchestrator(
                db=self._db,
                repositories=self._repos,
                tool_registry=session_registry,
                memory_store=self._memory_store,
            )
            session = session_orchestrator.create_session(config=config)

            full_text = ""
            tokens = 0

            try:
                async for event in session_orchestrator.send_message(
                    session_id=session.id, conversation_id=conv.id,
                    content=task.prompt, config=config,
                ):
                    if event.type == StreamEventType.TEXT_DELTA and event.text:
                        full_text += event.text
                    elif event.type == StreamEventType.DONE:
                        usage = event.usage or {}
                        tokens = usage.get("input", 0) + usage.get("output", 0)
                    elif event.type == StreamEventType.ERROR:
                        raise RuntimeError(event.error or "Agent error")
            finally:
                session_orchestrator.close_session(session.id)

            await self._repos.scheduled_tasks.complete_run(
                run.id, status="completed",
                response=full_text, tokens_used=tokens,
            )

            if self._webhook_dispatcher:
                await self._webhook_dispatcher.dispatch(
                    agent_id=agent.id,
                    event="cron.completed",
                    payload={
                        "task_id": task.id, "task_name": task.name,
                        "response": full_text, "conversation_id": conv.id,
                        "tokens_used": tokens,
                    },
                )

            logger.info("Scheduled task completed",
                        task_id=task.id, tokens=tokens,
                        response_preview=full_text[:100])

        except Exception as e:
            logger.error("Scheduled task failed", task_id=task.id, error=str(e))
            await self._repos.scheduled_tasks.complete_run(
                run.id, status="failed", error=str(e),
            )
        finally:
            # Always clean up MCP servers
            if mcp_clients:
                await stop_mcp_servers(mcp_clients)

        await self._repos.scheduled_tasks.mark_run(task.id)
