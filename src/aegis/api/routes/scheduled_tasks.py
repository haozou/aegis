"""Scheduled task routes — CRUD."""

from __future__ import annotations

from typing import Any

from croniter import croniter
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from ...auth.dependencies import get_current_user
from ...auth.models import User
from ...storage.repositories.scheduled_tasks import ScheduledTaskCreate
from ...utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["schedules"])


class CreateScheduleRequest(BaseModel):
    name: str = ""
    cron_expr: str  # e.g. "0 9 * * *"
    prompt: str
    timezone: str = "UTC"


class UpdateScheduleRequest(BaseModel):
    name: str | None = None
    cron_expr: str | None = None
    prompt: str | None = None
    is_active: bool | None = None


@router.get("/agents/{agent_id}/schedules")
async def list_schedules(
    agent_id: str,
    request: Request,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    repos = request.app.state.repositories
    agent = await repos.agents.get(agent_id)
    if not agent or agent.user_id != user.id:
        raise HTTPException(status_code=404, detail="Agent not found")

    tasks = await repos.scheduled_tasks.list_by_agent(agent_id)
    return {
        "schedules": [t.model_dump() for t in tasks],
        "count": len(tasks),
    }


@router.post("/agents/{agent_id}/schedules", status_code=201)
async def create_schedule(
    agent_id: str,
    data: CreateScheduleRequest,
    request: Request,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    repos = request.app.state.repositories
    agent = await repos.agents.get(agent_id)
    if not agent or agent.user_id != user.id:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Validate cron expression
    if not croniter.is_valid(data.cron_expr):
        raise HTTPException(status_code=422, detail=f"Invalid cron expression: {data.cron_expr}")

    task = await repos.scheduled_tasks.create(ScheduledTaskCreate(
        agent_id=agent_id, user_id=user.id,
        name=data.name, cron_expr=data.cron_expr,
        prompt=data.prompt, timezone=data.timezone,
    ))

    logger.info("Schedule created", task_id=task.id, cron=task.cron_expr, agent_id=agent_id)
    return {"schedule": task.model_dump()}


@router.delete("/agents/{agent_id}/schedules/{task_id}", status_code=204)
async def delete_schedule(
    agent_id: str,
    task_id: str,
    request: Request,
    user: User = Depends(get_current_user),
) -> None:
    repos = request.app.state.repositories
    task = await repos.scheduled_tasks.get(task_id)
    if not task or task.user_id != user.id or task.agent_id != agent_id:
        raise HTTPException(status_code=404, detail="Schedule not found")
    await repos.scheduled_tasks.delete(task_id)


@router.patch("/agents/{agent_id}/schedules/{task_id}")
async def update_schedule(
    agent_id: str,
    task_id: str,
    data: UpdateScheduleRequest,
    request: Request,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    repos = request.app.state.repositories
    task = await repos.scheduled_tasks.get(task_id)
    if not task or task.user_id != user.id or task.agent_id != agent_id:
        raise HTTPException(status_code=404, detail="Schedule not found")

    if data.cron_expr and not croniter.is_valid(data.cron_expr):
        raise HTTPException(status_code=422, detail=f"Invalid cron expression: {data.cron_expr}")

    updated = await repos.scheduled_tasks.update(
        task_id,
        name=data.name,
        cron_expr=data.cron_expr,
        prompt=data.prompt,
        is_active=data.is_active,
    )

    return {"schedule": updated.model_dump()}


@router.get("/agents/{agent_id}/schedules/{task_id}/runs")
async def list_runs(
    agent_id: str,
    task_id: str,
    request: Request,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    repos = request.app.state.repositories
    task = await repos.scheduled_tasks.get(task_id)
    if not task or task.user_id != user.id:
        raise HTTPException(status_code=404, detail="Schedule not found")

    runs = await repos.scheduled_tasks.list_runs(task_id)
    return {
        "runs": [r.model_dump() for r in runs],
        "count": len(runs),
    }
