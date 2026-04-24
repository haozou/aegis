"""Webhook repository."""

from __future__ import annotations

import json
import secrets
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from ...utils.ids import new_id
from ...utils.logging import get_logger
from ..database import Database

logger = get_logger(__name__)


class Webhook(BaseModel):
    id: str
    agent_id: str
    user_id: str
    slug: str
    name: str = ""
    direction: str = "inbound"
    url: str | None = None
    events: list[str] = Field(default_factory=list)
    secret: str | None = None
    is_active: bool = True
    created_at: str
    updated_at: str


class WebhookCreate(BaseModel):
    agent_id: str
    user_id: str
    name: str = ""
    direction: str = "inbound"
    url: str | None = None
    events: list[str] = Field(default_factory=list)
    secret: str | None = None


class WebhookDelivery(BaseModel):
    id: str
    webhook_id: str
    direction: str
    payload: dict[str, Any] = Field(default_factory=dict)
    response_text: str | None = None
    status_code: int | None = None
    error: str | None = None
    created_at: str


class WebhookRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def create(self, data: WebhookCreate) -> Webhook:
        wh_id = new_id("wh")
        slug = f"{new_id('hook')}"
        now = datetime.now(timezone.utc).isoformat()
        wh_secret = data.secret or secrets.token_urlsafe(24)

        await self.db.execute(
            """INSERT INTO webhooks (id, agent_id, user_id, slug, name, direction, url, events, secret, created_at, updated_at)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)""",
            (wh_id, data.agent_id, data.user_id, slug, data.name,
             data.direction, data.url, json.dumps(data.events),
             wh_secret, now, now),
        )
        await self.db.commit()

        return Webhook(
            id=wh_id, agent_id=data.agent_id, user_id=data.user_id,
            slug=slug, name=data.name, direction=data.direction,
            url=data.url, events=data.events, secret=wh_secret,
            created_at=now, updated_at=now,
        )

    async def get(self, webhook_id: str) -> Webhook | None:
        row = await self.db.fetchone("SELECT * FROM webhooks WHERE id = $1", (webhook_id,))
        return self._row_to_model(row) if row else None

    async def get_by_slug(self, slug: str) -> Webhook | None:
        row = await self.db.fetchone(
            "SELECT * FROM webhooks WHERE slug = $1 AND is_active = TRUE", (slug,)
        )
        return self._row_to_model(row) if row else None

    async def list_by_agent(self, agent_id: str, direction: str | None = None) -> list[Webhook]:
        if direction:
            rows = await self.db.fetchall(
                "SELECT * FROM webhooks WHERE agent_id = $1 AND direction = $2 ORDER BY created_at DESC",
                (agent_id, direction),
            )
        else:
            rows = await self.db.fetchall(
                "SELECT * FROM webhooks WHERE agent_id = $1 ORDER BY created_at DESC",
                (agent_id,),
            )
        return [self._row_to_model(r) for r in rows]

    async def list_outbound_for_agent(self, agent_id: str, event: str) -> list[Webhook]:
        """Get active outbound webhooks for an agent that subscribe to a given event."""
        rows = await self.db.fetchall(
            "SELECT * FROM webhooks WHERE agent_id = $1 AND direction = $2 AND is_active = TRUE",
            (agent_id, "outbound"),
        )
        result = []
        for r in rows:
            wh = self._row_to_model(r)
            if not wh.events or event in wh.events:
                result.append(wh)
        return result

    async def delete(self, webhook_id: str) -> bool:
        row = await self.db.fetchone("SELECT id FROM webhooks WHERE id = $1", (webhook_id,))
        if not row:
            return False
        await self.db.execute("DELETE FROM webhooks WHERE id = $1", (webhook_id,))
        await self.db.commit()
        return True

    async def log_delivery(
        self,
        webhook_id: str,
        direction: str,
        payload: dict[str, Any],
        response_text: str | None = None,
        status_code: int | None = None,
        error: str | None = None,
    ) -> WebhookDelivery:
        delivery_id = new_id("whd")
        now = datetime.now(timezone.utc).isoformat()
        await self.db.execute(
            """INSERT INTO webhook_deliveries (id, webhook_id, direction, payload, response_text, status_code, error, created_at)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8)""",
            (delivery_id, webhook_id, direction, json.dumps(payload),
             response_text, status_code, error, now),
        )
        await self.db.commit()
        return WebhookDelivery(
            id=delivery_id, webhook_id=webhook_id, direction=direction,
            payload=payload, response_text=response_text,
            status_code=status_code, error=error, created_at=now,
        )

    async def list_deliveries(self, webhook_id: str, limit: int = 50) -> list[WebhookDelivery]:
        rows = await self.db.fetchall(
            "SELECT * FROM webhook_deliveries WHERE webhook_id = $1 ORDER BY created_at DESC LIMIT $2",
            (webhook_id, limit),
        )
        return [self._delivery_to_model(r) for r in rows]

    def _row_to_model(self, row: Any) -> Webhook:
        events = row["events"]
        if isinstance(events, str):
            try:
                events = json.loads(events)
            except (json.JSONDecodeError, TypeError):
                events = []
        return Webhook(
            id=row["id"], agent_id=row["agent_id"], user_id=row["user_id"],
            slug=row["slug"], name=row["name"], direction=row["direction"],
            url=row["url"], events=events or [], secret=row["secret"],
            is_active=bool(row["is_active"]),
            created_at=str(row["created_at"]), updated_at=str(row["updated_at"]),
        )

    def _delivery_to_model(self, row: Any) -> WebhookDelivery:
        payload = row["payload"]
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except (json.JSONDecodeError, TypeError):
                payload = {}
        return WebhookDelivery(
            id=row["id"], webhook_id=row["webhook_id"],
            direction=row["direction"], payload=payload or {},
            response_text=row["response_text"],
            status_code=row["status_code"], error=row["error"],
            created_at=str(row["created_at"]),
        )
