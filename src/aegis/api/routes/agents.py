"""Agent routes — CRUD with tenant isolation."""

from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from ...auth.dependencies import get_current_user
from ...auth.models import User
from ...storage.repositories.agents import AgentCreate, AgentUpdate
from ...utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/agents", tags=["agents"])


class CreateAgentRequest(BaseModel):
    """API request body for creating an agent."""
    name: str = Field(min_length=1, max_length=100)
    slug: str | None = None  # auto-generated from name if not provided
    description: str = ""
    provider: str = ""   # not used for routing; kept for DB compat
    model: str = "claude-sonnet-4-5"
    temperature: float = 0.7
    max_tokens: int = 4096
    system_prompt: str = ""
    enable_memory: bool = False
    enable_skills: bool = False
    max_tool_iterations: int = 50
    allowed_tools: list[str] = Field(
        default_factory=lambda: [
            "web_search", "web_fetch", "bash", "file_read", "file_write", "file_list",
            "manage_schedules", "knowledge_base", "delegate_to_agent",
            "video_probe", "video_cut", "video_concat", "video_add_audio",
            "video_thumbnail", "video_export", "video_overlay_text", "video_speed",
            "image_generate",
            "file_export",
            "python",
        ]
    )


class UpdateAgentRequest(BaseModel):
    """API request body for updating an agent."""
    name: str | None = None
    description: str | None = None
    status: str | None = None
    provider: str | None = None
    model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    system_prompt: str | None = None
    enable_memory: bool | None = None
    enable_skills: bool | None = None
    max_tool_iterations: int | None = None
    allowed_tools: list[str] | None = None
    metadata: dict[str, Any] | None = None


def _slugify(name: str) -> str:
    """Convert a name to a URL-safe slug."""
    slug = name.lower().strip()
    slug = re.sub(r'[^a-z0-9]+', '-', slug)
    slug = slug.strip('-')
    return slug[:50] or "agent"


@router.get("")
async def list_agents(
    request: Request,
    user: User = Depends(get_current_user),
    status_filter: str | None = None,
) -> dict[str, Any]:
    """List all agents for the current user."""
    repos = request.app.state.repositories
    agents = await repos.agents.list_by_user(user.id, status=status_filter)
    return {
        "agents": [a.model_dump() for a in agents],
        "count": len(agents),
    }


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_agent(
    data: CreateAgentRequest,
    request: Request,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Create a new agent."""
    repos = request.app.state.repositories

    slug = data.slug or _slugify(data.name)

    # Check for slug conflict
    existing = await repos.agents.get_by_slug(user.id, slug)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Agent with slug '{slug}' already exists",
        )

    agent = await repos.agents.create(AgentCreate(
        user_id=user.id,
        name=data.name,
        slug=slug,
        description=data.description,
        provider=data.provider,
        model=data.model,
        temperature=data.temperature,
        max_tokens=data.max_tokens,
        system_prompt=data.system_prompt,
        enable_memory=data.enable_memory,
        enable_skills=data.enable_skills,
        max_tool_iterations=data.max_tool_iterations,
        allowed_tools=data.allowed_tools,
    ))

    logger.info("Agent created", agent_id=agent.id, name=agent.name, user_id=user.id)
    return {"agent": agent.model_dump()}


@router.get("/{agent_id}")
async def get_agent(
    agent_id: str,
    request: Request,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Get a specific agent."""
    repos = request.app.state.repositories
    agent = await repos.agents.get(agent_id)

    if agent is None or agent.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found",
        )

    return {"agent": agent.model_dump()}


@router.patch("/{agent_id}")
async def update_agent(
    agent_id: str,
    data: UpdateAgentRequest,
    request: Request,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Update an agent's configuration."""
    repos = request.app.state.repositories
    agent = await repos.agents.get(agent_id)

    if agent is None or agent.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found",
        )

    updated = await repos.agents.update(agent_id, AgentUpdate(**data.model_dump(exclude_none=True)))
    return {"agent": updated.model_dump() if updated else agent.model_dump()}


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(
    agent_id: str,
    request: Request,
    user: User = Depends(get_current_user),
) -> None:
    """Delete an agent."""
    repos = request.app.state.repositories
    agent = await repos.agents.get(agent_id)

    if agent is None or agent.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found",
        )

    await repos.agents.delete(agent_id)
    logger.info("Agent deleted", agent_id=agent_id, user_id=user.id)


@router.post("/{agent_id}/clone", status_code=status.HTTP_201_CREATED)
async def clone_agent(
    agent_id: str,
    request: Request,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Clone an agent — copies all config, tools, MCP servers, and metadata."""
    repos = request.app.state.repositories
    agent = await repos.agents.get(agent_id)

    if agent is None or agent.user_id != user.id:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Generate unique slug
    base_slug = f"{agent.slug}-copy"
    slug = base_slug
    counter = 1
    while await repos.agents.get_by_slug(user.id, slug):
        slug = f"{base_slug}-{counter}"
        counter += 1

    cloned = await repos.agents.create(AgentCreate(
        user_id=user.id,
        name=f"{agent.name} (Copy)",
        slug=slug,
        description=agent.description,
        provider=agent.provider,
        model=agent.model,
        temperature=agent.temperature,
        max_tokens=agent.max_tokens,
        system_prompt=agent.system_prompt,
        enable_memory=agent.enable_memory,
        enable_skills=agent.enable_skills,
        max_tool_iterations=agent.max_tool_iterations,
        allowed_tools=agent.allowed_tools,
    ))

    # Copy metadata (MCP servers, etc.)
    if agent.metadata:
        await repos.agents.update(cloned.id, AgentUpdate(metadata=agent.metadata))
        cloned = await repos.agents.get(cloned.id)

    logger.info("Agent cloned", source_id=agent_id, new_id=cloned.id, user_id=user.id)
    return {"agent": cloned.model_dump() if cloned else {}}


@router.get("/{agent_id}/usage")
async def get_agent_usage(
    agent_id: str,
    request: Request,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Get token usage statistics for an agent."""
    repos = request.app.state.repositories
    agent = await repos.agents.get(agent_id)
    if not agent or agent.user_id != user.id:
        raise HTTPException(status_code=404, detail="Agent not found")

    db = request.app.state.db
    is_pg = db.backend == "postgresql"

    # Total tokens across all conversations
    total_row = await db.fetchone(
        "SELECT COALESCE(SUM(m.tokens_used), 0) as total_tokens, COUNT(m.id) as message_count "
        "FROM messages m JOIN conversations c ON m.conversation_id = c.id "
        "WHERE c.agent_id = $1 AND m.role = $2",
        (agent_id, "assistant"),
    )
    total_tokens = total_row["total_tokens"] if total_row else 0
    message_count = total_row["message_count"] if total_row else 0

    # Conversation count
    conv_row = await db.fetchone(
        "SELECT COUNT(id) as count FROM conversations WHERE agent_id = $1",
        (agent_id,),
    )
    conversation_count = conv_row["count"] if conv_row else 0

    # Recent usage (last 7 days) — use DB-appropriate date function
    recent_sql = (
        "SELECT COALESCE(SUM(m.tokens_used), 0) as tokens "
        "FROM messages m JOIN conversations c ON m.conversation_id = c.id "
        "WHERE c.agent_id = $1 AND m.role = $2 AND m.created_at > "
    )
    if is_pg:
        recent_sql += "NOW() - INTERVAL '7 days'"
    else:
        recent_sql += "datetime('now', '-7 days')"

    recent_row = await db.fetchone(recent_sql, (agent_id, "assistant"))
    recent_tokens = recent_row["tokens"] if recent_row else 0

    return {
        "agent_id": agent_id,
        "total_tokens": total_tokens,
        "message_count": message_count,
        "conversation_count": conversation_count,
        "recent_tokens_7d": recent_tokens,
    }


@router.get("/{agent_id}/conversations")
async def list_agent_conversations(
    agent_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    """List conversations for a specific agent."""
    repos = request.app.state.repositories
    agent = await repos.agents.get(agent_id)

    if agent is None or agent.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found",
        )

    conversations = await repos.conversations.list_all(
        user_id=user.id, agent_id=agent_id, limit=limit, offset=offset,
    )
    return {
        "conversations": [c.model_dump() for c in conversations],
        "count": len(conversations),
    }


# ── MCP Server Management ────────────────────────────


class MCPServerConfig(BaseModel):
    id: str = Field(min_length=1, max_length=50, pattern=r"^[a-zA-Z0-9_-]+$")
    transport: str = ""  # "stdio", "http", or "" (auto-detect)
    # stdio
    command: str = ""
    args: list[str] = []
    env: dict[str, str] = {}
    # http
    url: str = ""
    headers: dict[str, str] = {}
    # common
    enabled: bool = True
    enabled_tools: list[str] = []  # empty = all tools; otherwise only these are registered


@router.get("/{agent_id}/mcp-servers")
async def list_mcp_servers(
    agent_id: str,
    request: Request,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    repos = request.app.state.repositories
    agent = await repos.agents.get(agent_id)
    if not agent or agent.user_id != user.id:
        raise HTTPException(status_code=404, detail="Agent not found")

    servers = agent.metadata.get("mcp_servers", [])
    return {"mcp_servers": servers, "count": len(servers)}


@router.post("/{agent_id}/mcp-servers", status_code=201)
async def add_mcp_server(
    agent_id: str,
    data: MCPServerConfig,
    request: Request,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    repos = request.app.state.repositories
    agent = await repos.agents.get(agent_id)
    if not agent or agent.user_id != user.id:
        raise HTTPException(status_code=404, detail="Agent not found")

    servers = agent.metadata.get("mcp_servers", [])

    # Check for duplicate id
    if any(s.get("id") == data.id for s in servers):
        raise HTTPException(status_code=409, detail=f"MCP server '{data.id}' already exists")

    servers.append(data.model_dump())
    metadata = {**agent.metadata, "mcp_servers": servers}

    await repos.agents.update(agent_id, AgentUpdate(metadata=metadata))
    logger.info("MCP server added", agent_id=agent_id, server_id=data.id)

    return {"mcp_servers": servers, "count": len(servers)}


class MCPProbeRequest(BaseModel):
    """Probe an MCP server to discover its tools."""
    command: str = ""
    args: list[str] = []
    env: dict[str, str] = {}
    url: str = ""
    headers: dict[str, str] = {}
    transport: str = ""
    oauth_token: str = ""


@router.post("/{agent_id}/mcp-probe")
async def probe_mcp_server(
    agent_id: str,
    data: MCPProbeRequest,
    request: Request,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Connect to an MCP server temporarily and list its available tools.

    Does NOT save — just discovers tools so the user can pick which to enable.
    For already-saved servers, tries to reuse cached tool lists if probe fails.
    """
    from ...tools.mcp_client import create_mcp_client

    repos = request.app.state.repositories
    agent = await repos.agents.get(agent_id)
    if not agent or agent.user_id != user.id:
        raise HTTPException(status_code=404, detail="Agent not found")

    oauth_token = data.oauth_token
    if not oauth_token and data.url:
        servers = agent.metadata.get("mcp_servers", [])
        for s in servers:
            if s.get("url") == data.url and s.get("oauth_token"):
                oauth_token = s["oauth_token"]
                break

    try:
        client = create_mcp_client(
            server_id="probe", command=data.command, args=data.args,
            env=data.env, url=data.url, headers=data.headers,
            transport_type=data.transport, oauth_token=oauth_token,
        )
        await client.start()
        tools = await client.list_tools()
        await client.stop()

        return {
            "tools": [
                {"name": t.name, "description": t.description, "input_schema": t.input_schema}
                for t in tools
            ],
            "count": len(tools),
        }
    except Exception as e:
        # Fallback: if this is an already-saved server, return its last known tools
        # so the user can still manage tool selection without re-probing
        servers = agent.metadata.get("mcp_servers", [])
        for s in servers:
            cmd_match = s.get("command") == data.command and s.get("url", "") == data.url
            if cmd_match and s.get("enabled_tools"):
                logger.warning("Probe failed, using cached tool list", error=str(e))
                return {
                    "tools": [{"name": t, "description": "", "input_schema": {}} for t in s["enabled_tools"]],
                    "count": len(s["enabled_tools"]),
                    "cached": True,
                }
        raise HTTPException(status_code=400, detail=f"Failed to probe MCP server: {e}")


@router.delete("/{agent_id}/mcp-servers/{server_id}", status_code=204)
async def remove_mcp_server(
    agent_id: str,
    server_id: str,
    request: Request,
    user: User = Depends(get_current_user),
) -> None:
    repos = request.app.state.repositories
    agent = await repos.agents.get(agent_id)
    if not agent or agent.user_id != user.id:
        raise HTTPException(status_code=404, detail="Agent not found")

    servers = agent.metadata.get("mcp_servers", [])
    new_servers = [s for s in servers if s.get("id") != server_id]

    if len(new_servers) == len(servers):
        raise HTTPException(status_code=404, detail="MCP server not found")

    metadata = {**agent.metadata, "mcp_servers": new_servers}
    await repos.agents.update(agent_id, AgentUpdate(metadata=metadata))
    logger.info("MCP server removed", agent_id=agent_id, server_id=server_id)


class UpdateMCPServerRequest(BaseModel):
    command: str | None = None
    args: list[str] | None = None
    env: dict[str, str] | None = None
    url: str | None = None
    enabled: bool | None = None


@router.patch("/{agent_id}/mcp-servers/{server_id}")
async def update_mcp_server(
    agent_id: str,
    server_id: str,
    data: UpdateMCPServerRequest,
    request: Request,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Update an existing MCP server's configuration (command, args, env, url)."""
    repos = request.app.state.repositories
    agent = await repos.agents.get(agent_id)
    if not agent or agent.user_id != user.id:
        raise HTTPException(status_code=404, detail="Agent not found")

    servers = agent.metadata.get("mcp_servers", [])
    found = False
    for s in servers:
        if s.get("id") == server_id:
            if data.command is not None:
                s["command"] = data.command
            if data.args is not None:
                s["args"] = data.args
            if data.env is not None:
                s["env"] = data.env
            if data.url is not None:
                s["url"] = data.url
            if data.enabled is not None:
                s["enabled"] = data.enabled
            found = True
            break

    if not found:
        raise HTTPException(status_code=404, detail="MCP server not found")

    metadata = {**agent.metadata, "mcp_servers": servers}
    await repos.agents.update(agent_id, AgentUpdate(metadata=metadata))
    logger.info("MCP server updated", agent_id=agent_id, server_id=server_id)

    return {"mcp_servers": servers, "count": len(servers)}


class UpdateMCPToolsRequest(BaseModel):
    enabled_tools: list[str] = []


@router.patch("/{agent_id}/mcp-servers/{server_id}/tools")
async def update_mcp_server_tools(
    agent_id: str,
    server_id: str,
    data: UpdateMCPToolsRequest,
    request: Request,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Update which tools are enabled for a specific MCP server."""
    repos = request.app.state.repositories
    agent = await repos.agents.get(agent_id)
    if not agent or agent.user_id != user.id:
        raise HTTPException(status_code=404, detail="Agent not found")

    servers = agent.metadata.get("mcp_servers", [])
    found = False
    for s in servers:
        if s.get("id") == server_id:
            s["enabled_tools"] = data.enabled_tools
            found = True
            break

    if not found:
        raise HTTPException(status_code=404, detail="MCP server not found")

    metadata = {**agent.metadata, "mcp_servers": servers}
    await repos.agents.update(agent_id, AgentUpdate(metadata=metadata))
    logger.info("MCP server tools updated", agent_id=agent_id, server_id=server_id,
                tool_count=len(data.enabled_tools))

    return {"mcp_servers": servers, "count": len(servers)}


@router.get("/{agent_id}/mcp-servers/{server_id}/auth")
async def mcp_oauth_start(
    agent_id: str,
    server_id: str,
    request: Request,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Start OAuth flow for an HTTP MCP server.

    1. Discovers OAuth metadata from the MCP server
    2. Dynamically registers a client (if registration endpoint exists)
    3. Generates PKCE code_verifier/code_challenge
    4. Returns a ready-to-open authorization URL
    """
    import hashlib
    import base64
    import secrets as sec

    from ...tools.mcp_client import discover_oauth_metadata

    repos = request.app.state.repositories
    agent = await repos.agents.get(agent_id)
    if not agent or agent.user_id != user.id:
        raise HTTPException(status_code=404, detail="Agent not found")

    servers = agent.metadata.get("mcp_servers", [])
    server_cfg = next((s for s in servers if s.get("id") == server_id), None)
    if not server_cfg or not server_cfg.get("url"):
        raise HTTPException(status_code=404, detail="MCP server not found or not HTTP type")

    metadata = await discover_oauth_metadata(server_cfg["url"])
    if not metadata:
        raise HTTPException(status_code=404, detail="MCP server does not support OAuth")

    base_url = str(request.base_url).rstrip("/")
    redirect_uri = f"{base_url}/api/mcp-oauth/callback"

    # Dynamic Client Registration (if supported)
    client_id = server_cfg.get("oauth_client_id", "")
    registration_endpoint = metadata.get("registration_endpoint", "")

    if not client_id and registration_endpoint:
        import httpx as hx
        # Use the server's supported auth method and grant types
        supported_auth = metadata.get("token_endpoint_auth_methods_supported", ["client_secret_post"])
        auth_method = supported_auth[0] if supported_auth else "client_secret_post"
        supported_grants = metadata.get("grant_types_supported", ["authorization_code"])

        try:
            async with hx.AsyncClient(timeout=15) as client:
                reg_resp = await client.post(registration_endpoint, json={
                    "client_name": "Aegis Agent Platform",
                    "redirect_uris": [redirect_uri],
                    "grant_types": supported_grants,
                    "response_types": ["code"],
                    "token_endpoint_auth_method": auth_method,
                })
                if reg_resp.status_code in (200, 201):
                    reg_data = reg_resp.json()
                    client_id = reg_data.get("client_id", "")
                    client_secret = reg_data.get("client_secret", "")
                    # Save client_id + secret back to agent metadata
                    for s in servers:
                        if s.get("id") == server_id:
                            s["oauth_client_id"] = client_id
                            if client_secret:
                                s["oauth_client_secret"] = client_secret
                            s["oauth_auth_method"] = auth_method
                    new_metadata = {**agent.metadata, "mcp_servers": servers}
                    await repos.agents.update(agent_id, AgentUpdate(metadata=new_metadata))
                    logger.info("OAuth client registered", server_id=server_id, client_id=client_id)
                else:
                    logger.warning("OAuth registration rejected",
                                   status=reg_resp.status_code, body=reg_resp.text[:300])
        except Exception as e:
            logger.warning("OAuth dynamic registration failed", error=str(e))

    if not client_id:
        raise HTTPException(status_code=400, detail="OAuth requires client_id but dynamic registration failed. Set oauth_client_id manually.")

    # Generate PKCE
    code_verifier = sec.token_urlsafe(64)
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode()).digest()
    ).rstrip(b"=").decode()

    # Build authorization URL
    auth_endpoint = metadata.get("authorization_endpoint", "")
    if not auth_endpoint:
        raise HTTPException(status_code=400, detail="No authorization_endpoint in OAuth metadata")

    from urllib.parse import urlencode
    scopes = metadata.get("scopes_supported", [])
    auth_params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    if scopes:
        auth_params["scope"] = " ".join(scopes)

    auth_url = f"{auth_endpoint}?{urlencode(auth_params)}"

    # Get client_secret if it was saved during registration
    client_secret = ""
    for s in servers:
        if s.get("id") == server_id:
            client_secret = s.get("oauth_client_secret", "")

    return {
        "auth_url": auth_url,
        "code_verifier": code_verifier,
        "client_id": client_id,
        "client_secret": client_secret,
        "token_endpoint": metadata.get("token_endpoint", ""),
        "redirect_uri": redirect_uri,
    }
