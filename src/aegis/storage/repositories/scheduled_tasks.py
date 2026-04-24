"""Scheduled task repository."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from croniter import croniter
from pydantic import BaseModel

from ...utils.ids import new_id
from ...utils.logging import get_logger
from ..database import Database

logger = get_logger(__name__)


class ScheduledTask(BaseModel):
    id: str
    agent_id: str
    user_id: str
    name: str = ""
    cron_expr: str
    prompt: str
    timezone: str = "UTC"
    is_active: bool = True
    last_run: str | None = None
    next_run: str | None = None
    created_at: str


class ScheduledTaskCreate(BaseModel):
    agent_id: str
    user_id: str
    name: str = ""
    cron_expr: str
    prompt: str
    timezone: str = "UTC"


class TaskRun(BaseModel):
    id: str
    task_id: str
    conversation_id: str | None = None
    status: str = "pending"
    response: str | None = None
    error: str | None = None
    tokens_used: int = 0
    started_at: str
    completed_at: str | None = None


def compute_next_run(cron_expr: str, tz: str = "UTC") -> str:
    """Compute the next run time from a cron expression."""
    now = datetime.now(timezone.utc)
    cron = croniter(cron_expr, now)
    next_dt = cron.get_next(datetime)
    return next_dt.isoformat()


class ScheduledTaskRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def create(self, data: ScheduledTaskCreate) -> ScheduledTask:
        task_id = new_id("task")
        now = datetime.now(timezone.utc).isoformat()
        next_run = compute_next_run(data.cron_expr, data.timezone)

        await self.db.execute(
            """INSERT INTO scheduled_tasks (id, agent_id, user_id, name, cron_expr, prompt, timezone, next_run, created_at)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)""",
            (task_id, data.agent_id, data.user_id, data.name,
             data.cron_expr, data.prompt, data.timezone, next_run, now),
        )
        await self.db.commit()

        return ScheduledTask(
            id=task_id, agent_id=data.agent_id, user_id=data.user_id,
            name=data.name, cron_expr=data.cron_expr, prompt=data.prompt,
            timezone=data.timezone, next_run=next_run, created_at=now,
        )

    async def get(self, task_id: str) -> ScheduledTask | None:
        row = await self.db.fetchone("SELECT * FROM scheduled_tasks WHERE id = $1", (task_id,))
        return self._row_to_model(row) if row else None

    async def list_by_agent(self, agent_id: str) -> list[ScheduledTask]:
        rows = await self.db.fetchall(
            "SELECT * FROM scheduled_tasks WHERE agent_id = $1 ORDER BY created_at DESC",
            (agent_id,),
        )
        return [self._row_to_model(r) for r in rows]

    async def get_due(self) -> list[ScheduledTask]:
        """Get all active tasks whose next_run is in the past (i.e., due now)."""
        now = datetime.now(timezone.utc).isoformat()
        rows = await self.db.fetchall(
            "SELECT * FROM scheduled_tasks WHERE is_active = TRUE AND next_run <= $1",
            (now,),
        )
        return [self._row_to_model(r) for r in rows]

    async def mark_run(self, task_id: str) -> None:
        """Update last_run and compute next_run."""
        task = await self.get(task_id)
        if not task:
            return
        now = datetime.now(timezone.utc).isoformat()
        next_run = compute_next_run(task.cron_expr, task.timezone)
        await self.db.execute(
            "UPDATE scheduled_tasks SET last_run = $1, next_run = $2 WHERE id = $3",
            (now, next_run, task_id),
        )
        await self.db.commit()

    async def delete(self, task_id: str) -> bool:
        row = await self.db.fetchone("SELECT id FROM scheduled_tasks WHERE id = $1", (task_id,))
        if not row:
            return False
        await self.db.execute("DELETE FROM scheduled_tasks WHERE id = $1", (task_id,))
        await self.db.commit()
        return True

    async def toggle(self, task_id: str, is_active: bool) -> ScheduledTask | None:
        await self.db.execute(
            "UPDATE scheduled_tasks SET is_active = $1 WHERE id = $2",
            (is_active, task_id),
        )
        await self.db.commit()
        return await self.get(task_id)

    async def update(
        self, task_id: str, *,
        name: str | None = None,
        cron_expr: str | None = None,
        prompt: str | None = None,
        is_active: bool | None = None,
    ) -> ScheduledTask | None:
        """Update schedule fields. Recomputes next_run if cron_expr changes."""
        task = await self.get(task_id)
        if not task:
            return None

        sets: list[str] = []
        params: list[object] = []
        idx = 1

        if name is not None:
            sets.append(f"name = ${idx}")
            params.append(name)
            idx += 1
        if cron_expr is not None:
            sets.append(f"cron_expr = ${idx}")
            params.append(cron_expr)
            idx += 1
            # Recompute next_run
            next_run = compute_next_run(cron_expr, task.timezone)
            sets.append(f"next_run = ${idx}")
            params.append(next_run)
            idx += 1
        if prompt is not None:
            sets.append(f"prompt = ${idx}")
            params.append(prompt)
            idx += 1
        if is_active is not None:
            sets.append(f"is_active = ${idx}")
            params.append(is_active)
            idx += 1

        if not sets:
            return task

        params.append(task_id)
        sql = f"UPDATE scheduled_tasks SET {', '.join(sets)} WHERE id = ${idx}"
        await self.db.execute(sql, tuple(params))
        await self.db.commit()
        return await self.get(task_id)

    async def log_run(
        self, task_id: str, conversation_id: str | None = None,
        status: str = "pending",
    ) -> TaskRun:
        run_id = new_id("run")
        now = datetime.now(timezone.utc).isoformat()
        await self.db.execute(
            """INSERT INTO task_runs (id, task_id, conversation_id, status, started_at)
               VALUES ($1, $2, $3, $4, $5)""",
            (run_id, task_id, conversation_id, status, now),
        )
        await self.db.commit()
        return TaskRun(id=run_id, task_id=task_id, conversation_id=conversation_id,
                       status=status, started_at=now)

    async def complete_run(
        self, run_id: str, status: str, response: str | None = None,
        error: str | None = None, tokens_used: int = 0,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        await self.db.execute(
            "UPDATE task_runs SET status = $1, response = $2, error = $3, tokens_used = $4, completed_at = $5 WHERE id = $6",
            (status, response, error, tokens_used, now, run_id),
        )
        await self.db.commit()

    async def list_runs(self, task_id: str, limit: int = 20) -> list[TaskRun]:
        rows = await self.db.fetchall(
            "SELECT * FROM task_runs WHERE task_id = $1 ORDER BY started_at DESC LIMIT $2",
            (task_id, limit),
        )
        return [self._run_to_model(r) for r in rows]

    def _row_to_model(self, row: Any) -> ScheduledTask:
        return ScheduledTask(
            id=row["id"], agent_id=row["agent_id"], user_id=row["user_id"],
            name=row["name"], cron_expr=row["cron_expr"], prompt=row["prompt"],
            timezone=row["timezone"], is_active=bool(row["is_active"]),
            last_run=str(row["last_run"]) if row["last_run"] else None,
            next_run=str(row["next_run"]) if row["next_run"] else None,
            created_at=str(row["created_at"]),
        )

    def _run_to_model(self, row: Any) -> TaskRun:
        return TaskRun(
            id=row["id"], task_id=row["task_id"],
            conversation_id=row["conversation_id"],
            status=row["status"], response=row["response"],
            error=row["error"], tokens_used=row["tokens_used"] or 0,
            started_at=str(row["started_at"]),
            completed_at=str(row["completed_at"]) if row["completed_at"] else None,
        )
