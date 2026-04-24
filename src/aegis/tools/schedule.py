"""Schedule management tool — lets the agent create, list, and delete scheduled tasks."""

from __future__ import annotations

import json
from typing import Any

from croniter import croniter

from ..utils.logging import get_logger
from .base import BaseTool
from .types import ToolContext, ToolResult

logger = get_logger(__name__)


class ScheduleTool(BaseTool):
    """Manage scheduled tasks for the current agent.

    The agent can create recurring tasks (cron jobs), list existing ones,
    or delete them. Each task runs on a cron schedule and sends a prompt
    to the agent automatically.
    """

    @property
    def name(self) -> str:
        return "manage_schedules"

    @property
    def description(self) -> str:
        return (
            "Create, list, or delete scheduled tasks for this agent. "
            "Scheduled tasks run automatically on a cron schedule and execute a prompt. "
            "Use this when the user asks you to do something periodically, "
            "e.g. 'check X every morning', 'send a report every Monday', 'remind me daily at 9am'."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["create", "list", "delete"],
                    "description": "Action to perform: create a new schedule, list existing ones, or delete one.",
                },
                "name": {
                    "type": "string",
                    "description": "Human-readable name for the schedule (for create action).",
                },
                "cron_expr": {
                    "type": "string",
                    "description": (
                        "Cron expression (5 fields: minute hour day-of-month month day-of-week). "
                        "Examples: '0 9 * * *' = daily at 9am, '0 9 * * 1' = every Monday 9am, "
                        "'*/30 * * * *' = every 30 minutes, '0 8 1 * *' = 1st of each month at 8am."
                    ),
                },
                "prompt": {
                    "type": "string",
                    "description": "The prompt/instruction to execute on each run (for create action).",
                },
                "timezone": {
                    "type": "string",
                    "description": "Timezone for the schedule (default: UTC). Examples: 'US/Eastern', 'Asia/Shanghai', 'Europe/London'.",
                },
                "schedule_id": {
                    "type": "string",
                    "description": "ID of the schedule to delete (for delete action).",
                },
            },
            "required": ["action"],
        }

    async def execute(self, context: ToolContext, **kwargs: Any) -> ToolResult:
        action = kwargs.get("action", "")
        repos = context.repositories

        if not repos:
            return ToolResult(output="Error: No repository access available.", is_error=True)
        if not context.agent_id:
            return ToolResult(output="Error: No agent_id in context.", is_error=True)

        try:
            if action == "create":
                return await self._create(context, repos, **kwargs)
            elif action == "list":
                return await self._list(context, repos)
            elif action == "delete":
                return await self._delete(context, repos, **kwargs)
            else:
                return ToolResult(output=f"Unknown action: {action}. Use 'create', 'list', or 'delete'.", is_error=True)
        except Exception as e:
            logger.error("Schedule tool error", action=action, error=str(e))
            return ToolResult(output=f"Error: {e}", is_error=True)

    async def _create(self, context: ToolContext, repos: Any, **kwargs: Any) -> ToolResult:
        from ..storage.repositories.scheduled_tasks import ScheduledTaskCreate

        cron_expr = kwargs.get("cron_expr", "")
        prompt = kwargs.get("prompt", "")
        name = kwargs.get("name", "")
        timezone = kwargs.get("timezone", "UTC")

        if not cron_expr:
            return ToolResult(output="Error: cron_expr is required for create action.", is_error=True)
        if not prompt:
            return ToolResult(output="Error: prompt is required for create action.", is_error=True)

        # Validate cron expression
        if not croniter.is_valid(cron_expr):
            return ToolResult(output=f"Error: Invalid cron expression '{cron_expr}'.", is_error=True)

        task = await repos.scheduled_tasks.create(ScheduledTaskCreate(
            agent_id=context.agent_id,
            user_id=context.user_id,
            name=name,
            cron_expr=cron_expr,
            prompt=prompt,
            timezone=timezone,
        ))

        logger.info("Schedule created by agent",
                     task_id=task.id, agent_id=context.agent_id, cron=cron_expr)

        # Compute next run for display
        from datetime import datetime
        cron = croniter(cron_expr, datetime.utcnow())
        next_run = cron.get_next(datetime).strftime("%Y-%m-%d %H:%M UTC")

        return ToolResult(output=json.dumps({
            "status": "created",
            "schedule_id": task.id,
            "name": name,
            "cron_expr": cron_expr,
            "prompt": prompt,
            "timezone": timezone,
            "next_run": next_run,
        }, indent=2))

    async def _list(self, context: ToolContext, repos: Any) -> ToolResult:
        tasks = await repos.scheduled_tasks.list_by_agent(context.agent_id)

        if not tasks:
            return ToolResult(output="No scheduled tasks found for this agent.")

        result = []
        for t in tasks:
            result.append({
                "id": t.id,
                "name": t.name,
                "cron_expr": t.cron_expr,
                "prompt": t.prompt[:100] + ("..." if len(t.prompt) > 100 else ""),
                "timezone": t.timezone,
                "enabled": t.enabled,
                "last_run": t.last_run_at.isoformat() if t.last_run_at else None,
                "next_run": t.next_run_at.isoformat() if t.next_run_at else None,
            })

        return ToolResult(output=json.dumps(result, indent=2))

    async def _delete(self, context: ToolContext, repos: Any, **kwargs: Any) -> ToolResult:
        schedule_id = kwargs.get("schedule_id", "")
        if not schedule_id:
            return ToolResult(output="Error: schedule_id is required for delete action.", is_error=True)

        task = await repos.scheduled_tasks.get(schedule_id)
        if not task or task.agent_id != context.agent_id:
            return ToolResult(output=f"Error: Schedule '{schedule_id}' not found.", is_error=True)

        await repos.scheduled_tasks.delete(schedule_id)
        logger.info("Schedule deleted by agent", task_id=schedule_id, agent_id=context.agent_id)

        return ToolResult(output=json.dumps({
            "status": "deleted",
            "schedule_id": schedule_id,
            "name": task.name,
        }))
