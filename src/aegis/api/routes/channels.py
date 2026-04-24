"""Channel connection routes — CRUD + inbound webhook endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from ...auth.dependencies import get_current_user
from ...auth.models import User
from ...storage.repositories.channels import (
    CHANNEL_TYPES,
    ChannelConnectionCreate,
    ChannelConnectionUpdate,
)
from ...utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["channels"])


class CreateChannelConnectionRequest(BaseModel):
    channel_type: str
    name: str = ""
    config: dict[str, Any] = {}
    is_active: bool = True


class UpdateChannelConnectionRequest(BaseModel):
    name: str | None = None
    config: dict[str, Any] | None = None
    is_active: bool | None = None


# ── CRUD (authenticated) ─────────────────────────────────────────────────────


@router.get("/agents/{agent_id}/channels")
async def list_channel_connections(
    agent_id: str,
    request: Request,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    repos = request.app.state.repositories
    agent = await repos.agents.get(agent_id)
    if not agent or agent.user_id != user.id:
        raise HTTPException(status_code=404, detail="Agent not found")

    connections = await repos.channels.list_by_agent(agent_id)
    return {
        "connections": [_redact(c.model_dump()) for c in connections],
        "count": len(connections),
    }


@router.post("/agents/{agent_id}/channels", status_code=201)
async def create_channel_connection(
    agent_id: str,
    data: CreateChannelConnectionRequest,
    request: Request,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    repos = request.app.state.repositories
    agent = await repos.agents.get(agent_id)
    if not agent or agent.user_id != user.id:
        raise HTTPException(status_code=404, detail="Agent not found")

    if data.channel_type not in CHANNEL_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown channel_type. Must be one of: {sorted(CHANNEL_TYPES)}",
        )

    conn = await repos.channels.create(
        ChannelConnectionCreate(
            agent_id=agent_id,
            user_id=user.id,
            channel_type=data.channel_type,
            name=data.name or data.channel_type.title(),
            config=data.config,
            is_active=data.is_active,
        )
    )

    # Start the adapter if active
    if conn.is_active:
        channel_manager = getattr(request.app.state, "channel_manager", None)
        if channel_manager:
            await channel_manager.reload_connection(conn.id)

    return {"connection": _redact(conn.model_dump())}


@router.get("/agents/{agent_id}/channels/{connection_id}")
async def get_channel_connection(
    agent_id: str,
    connection_id: str,
    request: Request,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    repos = request.app.state.repositories
    conn = await _get_owned_connection(repos, agent_id, connection_id, user.id)
    return {"connection": _redact(conn.model_dump())}


@router.patch("/agents/{agent_id}/channels/{connection_id}")
async def update_channel_connection(
    agent_id: str,
    connection_id: str,
    data: UpdateChannelConnectionRequest,
    request: Request,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    repos = request.app.state.repositories
    await _get_owned_connection(repos, agent_id, connection_id, user.id)

    updated = await repos.channels.update(
        connection_id,
        ChannelConnectionUpdate(
            name=data.name,
            config=data.config,
            is_active=data.is_active,
        ),
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Connection not found")

    channel_manager = getattr(request.app.state, "channel_manager", None)
    if channel_manager:
        if updated.is_active:
            await channel_manager.reload_connection(connection_id)
        else:
            await channel_manager.remove_connection(connection_id)

    return {"connection": _redact(updated.model_dump())}


@router.delete("/agents/{agent_id}/channels/{connection_id}", status_code=204)
async def delete_channel_connection(
    agent_id: str,
    connection_id: str,
    request: Request,
    user: User = Depends(get_current_user),
) -> None:
    repos = request.app.state.repositories
    await _get_owned_connection(repos, agent_id, connection_id, user.id)

    channel_manager = getattr(request.app.state, "channel_manager", None)
    if channel_manager:
        await channel_manager.remove_connection(connection_id)

    deleted = await repos.channels.delete(connection_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Connection not found")


# ── Inbound webhook endpoints (no auth — platform pushes here) ───────────────


@router.post("/channels/telegram/{connection_id}/webhook")
async def telegram_webhook(
    connection_id: str,
    request: Request,
) -> dict[str, Any]:
    """Telegram pushes updates here when a message is received."""
    channel_manager = getattr(request.app.state, "channel_manager", None)
    if channel_manager is None:
        raise HTTPException(status_code=503, detail="Channel manager not running")

    adapter = channel_manager.get_adapter(connection_id)
    if adapter is None:
        raise HTTPException(status_code=404, detail="Connection not active")

    # Verify secret token if configured
    repos = request.app.state.repositories
    conn = await repos.channels.get(connection_id)
    if conn:
        secret = conn.config.get("webhook_secret", "")
        if secret:
            header_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
            if header_secret != secret:
                raise HTTPException(status_code=403, detail="Invalid secret")

    update = await request.json()
    await adapter.handle_update(update)
    return {"ok": True}


@router.post("/channels/sms/{connection_id}/webhook")
async def sms_webhook(
    connection_id: str,
    request: Request,
) -> Any:
    """Twilio calls this when an SMS is received. Returns TwiML."""
    from fastapi.responses import Response

    channel_manager = getattr(request.app.state, "channel_manager", None)
    if channel_manager is None:
        return Response(content="<Response/>", media_type="text/xml")

    adapter = channel_manager.get_adapter(connection_id)
    if adapter is None:
        return Response(content="<Response/>", media_type="text/xml")

    form = await request.form()
    twiml = await adapter.handle_inbound(dict(form))
    return Response(content=twiml, media_type="text/xml")


@router.get("/channels/wechat/{connection_id}/webhook")
async def wechat_webhook_verify(
    connection_id: str,
    request: Request,
) -> Any:
    """WeChat server verification handshake (GET).

    WeChat sends: signature, timestamp, nonce, echostr
    We must return echostr verbatim if the signature is valid.
    """
    from fastapi.responses import PlainTextResponse

    channel_manager = getattr(request.app.state, "channel_manager", None)
    if channel_manager is None:
        raise HTTPException(status_code=503, detail="Channel manager not running")

    adapter = channel_manager.get_adapter(connection_id)
    if adapter is None:
        raise HTTPException(status_code=404, detail="Connection not active")

    params = request.query_params
    signature = params.get("signature", "")
    timestamp = params.get("timestamp", "")
    nonce = params.get("nonce", "")
    echostr = params.get("echostr", "")

    result = await adapter.handle_verify(timestamp, nonce, signature, echostr)
    if result is None:
        raise HTTPException(status_code=403, detail="Invalid signature")

    return PlainTextResponse(result)


@router.post("/channels/wechat/{connection_id}/webhook")
async def wechat_webhook(
    connection_id: str,
    request: Request,
) -> Any:
    """WeChat pushes XML messages here when a user sends a message."""
    from fastapi.responses import PlainTextResponse

    channel_manager = getattr(request.app.state, "channel_manager", None)
    if channel_manager is None:
        return PlainTextResponse("success")

    adapter = channel_manager.get_adapter(connection_id)
    if adapter is None:
        return PlainTextResponse("success")

    params = request.query_params
    signature = params.get("signature", "")
    timestamp = params.get("timestamp", "")
    nonce = params.get("nonce", "")

    body = await request.body()
    result = await adapter.handle_update(body, timestamp, nonce, signature)
    return PlainTextResponse(result)


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _get_owned_connection(repos: Any, agent_id: str, connection_id: str, user_id: str) -> Any:
    agent = await repos.agents.get(agent_id)
    if not agent or agent.user_id != user_id:
        raise HTTPException(status_code=404, detail="Agent not found")

    conn = await repos.channels.get(connection_id)
    if not conn or conn.agent_id != agent_id or conn.user_id != user_id:
        raise HTTPException(status_code=404, detail="Connection not found")

    return conn


def _redact(data: dict[str, Any]) -> dict[str, Any]:
    """Remove sensitive credential values from API responses (keep keys)."""
    SENSITIVE = frozenset({
        "bot_token", "imap_pass", "smtp_pass", "auth_token",
        "account_sid", "webhook_secret", "app_secret",
    })
    config = data.get("config", {})
    if isinstance(config, dict):
        data = {**data, "config": {
            k: ("***" if k in SENSITIVE and v else v)
            for k, v in config.items()
        }}
    return data
