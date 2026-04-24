"""MCP OAuth callback and token exchange."""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from ...auth.dependencies import get_current_user
from ...auth.models import User
from ...storage.repositories.agents import AgentUpdate
from ...utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["mcp-oauth"])


@router.get("/mcp-oauth/callback")
async def mcp_oauth_callback(request: Request, code: str = "", error: str = "") -> HTMLResponse:
    """OAuth callback — receives the authorization code and sends it to the opener window."""
    if error:
        return HTMLResponse(f"""
        <html><body><script>
            window.opener?.postMessage({{ type: 'mcp-oauth-error', error: '{error}' }}, '*');
            window.close();
        </script><p>OAuth error: {error}.</p></body></html>
        """)

    if not code:
        return HTMLResponse("<html><body><p>Missing authorization code.</p></body></html>")

    return HTMLResponse(f"""
    <html><body><script>
        window.opener?.postMessage({{ type: 'mcp-oauth-code', code: `{code}` }}, '*');
        window.close();
    </script><p>Authorization successful! This window will close.</p></body></html>
    """)


class TokenExchangeRequest(BaseModel):
    agent_id: str
    server_id: str
    code: str
    code_verifier: str


@router.post("/mcp-oauth/exchange")
async def mcp_oauth_exchange(
    data: TokenExchangeRequest,
    request: Request,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Exchange an OAuth code for an access token (server-side to avoid CORS).

    Stores the token in the MCP server config.
    """
    repos = request.app.state.repositories
    agent = await repos.agents.get(data.agent_id)
    if not agent or agent.user_id != user.id:
        raise HTTPException(status_code=404, detail="Agent not found")

    servers = agent.metadata.get("mcp_servers", [])
    server_cfg = next((s for s in servers if s.get("id") == data.server_id), None)
    if not server_cfg:
        raise HTTPException(status_code=404, detail="MCP server not found")

    # Get OAuth metadata
    from ...tools.mcp_client import discover_oauth_metadata
    metadata = await discover_oauth_metadata(server_cfg["url"])
    if not metadata:
        raise HTTPException(status_code=400, detail="Cannot discover OAuth metadata")

    token_endpoint = metadata.get("token_endpoint", "")
    if not token_endpoint:
        raise HTTPException(status_code=400, detail="No token endpoint")

    client_id = server_cfg.get("oauth_client_id", "")
    client_secret = server_cfg.get("oauth_client_secret", "")

    base_url = str(request.base_url).rstrip("/")
    redirect_uri = f"{base_url}/api/mcp-oauth/callback"

    # Exchange code for token
    token_params: dict[str, str] = {
        "grant_type": "authorization_code",
        "code": data.code,
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "code_verifier": data.code_verifier,
    }
    if client_secret:
        token_params["client_secret"] = client_secret

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(token_endpoint, data=token_params)
            if resp.status_code != 200:
                logger.error("OAuth token exchange failed", status=resp.status_code, body=resp.text[:300])
                raise HTTPException(status_code=400, detail=f"Token exchange failed: {resp.text[:200]}")
            token_data = resp.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=400, detail=f"Token exchange error: {e}")

    access_token = token_data.get("access_token", "")
    if not access_token:
        raise HTTPException(status_code=400, detail="No access_token in response")

    # Store the token in the MCP server config
    for s in servers:
        if s.get("id") == data.server_id:
            s["oauth_token"] = access_token
            if token_data.get("refresh_token"):
                s["oauth_refresh_token"] = token_data["refresh_token"]

    new_metadata = {**agent.metadata, "mcp_servers": servers}
    await repos.agents.update(data.agent_id, AgentUpdate(metadata=new_metadata))

    logger.info("OAuth token stored", server_id=data.server_id, agent_id=data.agent_id)
    return {"status": "ok", "message": "Token saved. Reconnect to the agent to use MCP tools."}


@router.api_route("/mcp-auth-proxy/{port}/{path:path}", methods=["GET", "POST"])
async def mcp_auth_proxy(port: int, path: str, request: Request) -> Any:
    """Proxy OAuth callbacks to MCP servers' localhost listeners inside Docker.

    When an MCP server starts a callback listener on localhost:XXXXX inside
    the container, the browser can't reach it directly. This endpoint proxies:
      browser → nginx :3000/mcp-auth-proxy/XXXXX/callback?code=...
      → API :8000/api/mcp-auth-proxy/XXXXX/callback?code=...
      → localhost:XXXXX/callback?code=...  (inside container)
    """
    if port < 1024 or port > 65535:
        raise HTTPException(status_code=400, detail="Invalid port")

    target_url = f"http://localhost:{port}/{path}"
    if request.url.query:
        target_url += f"?{request.url.query}"

    logger.info("MCP auth proxy", port=port, path=path)

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            if request.method == "POST":
                body = await request.body()
                resp = await client.post(
                    target_url,
                    content=body,
                    headers={"Content-Type": request.headers.get("content-type", "")},
                )
            else:
                resp = await client.get(target_url)

        # Return the response as-is (HTML page, redirect, etc.)
        from fastapi.responses import Response
        return Response(
            content=resp.content,
            status_code=resp.status_code,
            headers=dict(resp.headers),
        )
    except Exception as e:
        logger.error("MCP auth proxy failed", port=port, error=str(e))
        return HTMLResponse(
            f"<html><body><p>Auth callback failed: could not reach MCP server on port {port}.</p>"
            f"<p>Error: {e}</p></body></html>",
            status_code=502,
        )
