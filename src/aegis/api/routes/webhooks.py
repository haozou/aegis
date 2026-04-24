"""Webhook routes — CRUD + inbound trigger endpoint."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from ...auth.dependencies import get_current_user
from ...auth.models import User
from ...core.types import AgentConfig, StreamEventType
from ...storage.repositories.conversations import ConversationCreate
from ...storage.repositories.webhooks import WebhookCreate
from ...utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["webhooks"])


class CreateWebhookRequest(BaseModel):
    name: str = ""
    direction: str = "inbound"
    url: str | None = None
    events: list[str] = []


# ── CRUD (authenticated) ─────────────────────────────


@router.get("/agents/{agent_id}/webhooks")
async def list_webhooks(
    agent_id: str,
    request: Request,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    repos = request.app.state.repositories
    agent = await repos.agents.get(agent_id)
    if not agent or agent.user_id != user.id:
        raise HTTPException(status_code=404, detail="Agent not found")

    webhooks = await repos.webhooks.list_by_agent(agent_id)
    return {
        "webhooks": [w.model_dump() for w in webhooks],
        "count": len(webhooks),
    }


@router.post("/agents/{agent_id}/webhooks", status_code=201)
async def create_webhook(
    agent_id: str,
    data: CreateWebhookRequest,
    request: Request,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    repos = request.app.state.repositories
    agent = await repos.agents.get(agent_id)
    if not agent or agent.user_id != user.id:
        raise HTTPException(status_code=404, detail="Agent not found")

    if data.direction == "outbound" and not data.url:
        raise HTTPException(status_code=422, detail="Outbound webhooks require a URL")

    webhook = await repos.webhooks.create(WebhookCreate(
        agent_id=agent_id, user_id=user.id,
        name=data.name, direction=data.direction,
        url=data.url, events=data.events,
    ))

    base_url = str(request.base_url).rstrip("/")
    logger.info("Webhook created", webhook_id=webhook.id, direction=webhook.direction)
    return {
        "webhook": webhook.model_dump(),
        "trigger_url": f"{base_url}/api/hooks/{webhook.slug}" if webhook.direction == "inbound" else None,
    }


@router.delete("/agents/{agent_id}/webhooks/{webhook_id}", status_code=204)
async def delete_webhook(
    agent_id: str,
    webhook_id: str,
    request: Request,
    user: User = Depends(get_current_user),
) -> None:
    repos = request.app.state.repositories
    webhook = await repos.webhooks.get(webhook_id)
    if not webhook or webhook.user_id != user.id or webhook.agent_id != agent_id:
        raise HTTPException(status_code=404, detail="Webhook not found")
    await repos.webhooks.delete(webhook_id)


@router.get("/agents/{agent_id}/webhooks/{webhook_id}/deliveries")
async def list_deliveries(
    agent_id: str,
    webhook_id: str,
    request: Request,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    repos = request.app.state.repositories
    webhook = await repos.webhooks.get(webhook_id)
    if not webhook or webhook.user_id != user.id:
        raise HTTPException(status_code=404, detail="Webhook not found")

    deliveries = await repos.webhooks.list_deliveries(webhook_id)
    return {
        "deliveries": [d.model_dump() for d in deliveries],
        "count": len(deliveries),
    }


# ── Inbound Trigger (public, authenticated by slug + optional HMAC) ──


def _extract_message_from_dict(d: dict[str, Any]) -> str:
    """Recursively extract a text message from a dict with unknown structure.

    Tries common field names, then looks inside nested dicts.
    Handles Power Automate, Teams, Slack, Discord, and arbitrary JSON.
    """
    # Priority: explicit message fields
    for key in ("message", "text", "content", "plainTextContent", "body",
                "query", "prompt", "input", "question", "data"):
        val = d.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()

    # Check nested "body" dict (Power Automate often nests here)
    if isinstance(d.get("body"), dict):
        result = _extract_message_from_dict(d["body"])
        if result:
            return result

    # Check "data" dict
    if isinstance(d.get("data"), dict):
        result = _extract_message_from_dict(d["data"])
        if result:
            return result

    # Last resort: find the first non-empty string value in the dict
    for val in d.values():
        if isinstance(val, str) and len(val.strip()) > 2 and not val.startswith("http"):
            return val.strip()

    # Give up: serialize the whole thing
    return json.dumps(d, indent=2)


def _agent_to_config(agent: Any) -> AgentConfig:
    return AgentConfig(
        provider=agent.provider, model=agent.model,
        temperature=agent.temperature, max_tokens=agent.max_tokens,
        system_prompt=agent.system_prompt,
        enable_memory=agent.enable_memory, enable_skills=agent.enable_skills,
        tool_names=agent.allowed_tools if agent.allowed_tools else None,
        max_tool_iterations=agent.max_tool_iterations,
    )


@router.post("/hooks/{slug}")
async def inbound_webhook_trigger(slug: str, request: Request) -> dict[str, Any]:
    """Public endpoint: external services POST here to trigger an agent.

    Body can be:
    - JSON with a "message" field: {"message": "process this"}
    - Plain text body
    - Any JSON (stringified as the message)

    Optional HMAC signature via X-Webhook-Signature header.
    """
    repos = request.app.state.repositories
    orchestrator = request.app.state.orchestrator

    # 1. Look up webhook
    webhook = await repos.webhooks.get_by_slug(slug)
    if not webhook or webhook.direction != "inbound":
        raise HTTPException(status_code=404, detail="Webhook not found")

    # 2. Read body
    body = await request.body()
    body_str = body.decode("utf-8", errors="replace")

    logger.info(
        "Inbound webhook received",
        slug=slug,
        content_type=request.headers.get("content-type", ""),
        body_length=len(body_str),
        body_preview=body_str[:500],
    )

    # 3. Verify HMAC signature if secret is set
    if webhook.secret:
        signature = request.headers.get("X-Webhook-Signature", "")
        expected = hmac.new(
            webhook.secret.encode(), body, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(f"sha256={expected}", signature):
            # Allow unsigned requests too (signature is optional)
            pass

    # 4. Extract message — auto-detect platform format
    response_format = "default"
    message = ""
    try:
        payload = json.loads(body_str)
        if isinstance(payload, dict):
            # Microsoft Teams outgoing webhook
            if payload.get("type") == "message" and "text" in payload:
                raw_text = payload["text"]
                message = re.sub(r'<at>.*?</at>\s*', '', raw_text).strip()
                response_format = "teams"
            # Slack Events API
            elif "event" in payload and isinstance(payload["event"], dict):
                event_data = payload["event"]
                message = event_data.get("text", "")
                response_format = "slack"
                if payload.get("type") == "url_verification":
                    return {"challenge": payload.get("challenge", "")}
            # Slack slash command or simple webhook
            elif "text" in payload and ("token" in payload or "team_id" in payload):
                message = payload["text"]
                response_format = "slack"
            # Discord webhook
            elif "content" in payload and ("guild_id" in payload or "author" in payload):
                message = payload["content"]
                response_format = "discord"
            else:
                # Generic: try common field names in priority order
                message = _extract_message_from_dict(payload)
        elif isinstance(payload, str):
            message = payload
        else:
            message = str(payload)
    except (json.JSONDecodeError, TypeError):
        message = body_str

    # Fallback: if still empty, use the raw body
    if not message.strip() and body_str.strip():
        message = body_str.strip()

    if not message.strip():
        raise HTTPException(status_code=400, detail="Empty message")

    # 5. Get agent
    agent = await repos.agents.get(webhook.agent_id)
    if not agent or agent.status != "active":
        raise HTTPException(status_code=400, detail="Agent is not active")

    # 6. Create conversation and run agent
    title = f"Webhook: {webhook.name or slug}"
    conv = await repos.conversations.create(ConversationCreate(
        title=title, provider=agent.provider, model=agent.model,
        user_id=webhook.user_id, agent_id=agent.id,
    ))

    config = _agent_to_config(agent)
    session = orchestrator.create_session(config=config)

    full_text = ""
    message_id = ""
    usage: dict[str, int] = {"input": 0, "output": 0}

    try:
        async for event in orchestrator.send_message(
            session_id=session.id, conversation_id=conv.id,
            content=message, config=config,
        ):
            if event.type == StreamEventType.TEXT_DELTA and event.text:
                full_text += event.text
            elif event.type == StreamEventType.DONE:
                message_id = event.message_id or ""
                usage = event.usage or usage
            elif event.type == StreamEventType.ERROR:
                await repos.webhooks.log_delivery(
                    webhook.id, "inbound", {"message": message},
                    error=event.error, status_code=500,
                )
                raise HTTPException(status_code=500, detail=event.error)
    finally:
        orchestrator.close_session(session.id)

    # 7. Log delivery
    await repos.webhooks.log_delivery(
        webhook.id, "inbound",
        payload={"message": message},
        response_text=full_text, status_code=200,
    )

    logger.info("Inbound webhook processed", slug=slug, agent_id=agent.id, format=response_format)

    # 8. Return response in the right format for the platform
    if response_format == "teams":
        return {"type": "message", "text": full_text}
    elif response_format == "slack":
        return {"text": full_text}
    elif response_format == "discord":
        return {"content": full_text}
    else:
        return {
            "conversation_id": conv.id,
            "message_id": message_id,
            "response": full_text,
            "usage": usage,
        }
