"""Integration tests for API endpoints."""

import pytest
import pytest_asyncio
from httpx import AsyncClient


# ── Auth API ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_register(client: AsyncClient):
    resp = await client.post("/api/auth/register", json={
        "email": "new@test.com",
        "username": "newuser",
        "password": "password123",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["user"]["email"] == "new@test.com"
    assert "access_token" in data["tokens"]
    assert "refresh_token" in data["tokens"]


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient):
    await client.post("/api/auth/register", json={
        "email": "dup@test.com", "username": "dup1", "password": "password123",
    })
    resp = await client.post("/api/auth/register", json={
        "email": "dup@test.com", "username": "dup2", "password": "password123",
    })
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_register_short_username(client: AsyncClient):
    resp = await client.post("/api/auth/register", json={
        "email": "x@test.com", "username": "ab", "password": "password123",
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_register_short_password(client: AsyncClient):
    resp = await client.post("/api/auth/register", json={
        "email": "x@test.com", "username": "validname", "password": "short",
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_login(client: AsyncClient):
    await client.post("/api/auth/register", json={
        "email": "login@test.com", "username": "loginuser", "password": "password123",
    })
    resp = await client.post("/api/auth/login", json={
        "email": "login@test.com", "password": "password123",
    })
    assert resp.status_code == 200
    assert "access_token" in resp.json()["tokens"]


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient):
    await client.post("/api/auth/register", json={
        "email": "wrongpw@test.com", "username": "wrongpw", "password": "password123",
    })
    resp = await client.post("/api/auth/login", json={
        "email": "wrongpw@test.com", "password": "wrongpassword",
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_nonexistent_user(client: AsyncClient):
    resp = await client.post("/api/auth/login", json={
        "email": "nobody@test.com", "password": "password123",
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_me(client: AsyncClient, auth_headers: dict):
    resp = await client.get("/api/auth/me", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["user"]["email"] == "test@example.com"


@pytest.mark.asyncio
async def test_get_me_no_auth(client: AsyncClient):
    resp = await client.get("/api/auth/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token(client: AsyncClient):
    reg = await client.post("/api/auth/register", json={
        "email": "refresh@test.com", "username": "refreshuser", "password": "password123",
    })
    refresh_token = reg.json()["tokens"]["refresh_token"]
    resp = await client.post("/api/auth/refresh", headers={
        "Authorization": f"Bearer {refresh_token}",
    })
    assert resp.status_code == 200
    assert "access_token" in resp.json()["tokens"]


# ── Agents API ───────────────────────────────────────


@pytest.mark.asyncio
async def test_create_agent(client: AsyncClient, auth_headers: dict):
    resp = await client.post("/api/agents", json={
        "name": "My Bot",
        "system_prompt": "Be helpful.",
        "description": "A test bot",
    }, headers=auth_headers)
    assert resp.status_code == 201
    agent = resp.json()["agent"]
    assert agent["name"] == "My Bot"
    assert agent["slug"] == "my-bot"
    assert agent["status"] == "active"


@pytest.mark.asyncio
async def test_list_agents(client: AsyncClient, auth_headers: dict, test_agent: dict):
    resp = await client.get("/api/agents", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["count"] >= 1


@pytest.mark.asyncio
async def test_get_agent(client: AsyncClient, auth_headers: dict, test_agent: dict):
    resp = await client.get(f"/api/agents/{test_agent['id']}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["agent"]["id"] == test_agent["id"]


@pytest.mark.asyncio
async def test_get_agent_not_found(client: AsyncClient, auth_headers: dict):
    resp = await client.get("/api/agents/agt_nonexistent", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_agent(client: AsyncClient, auth_headers: dict, test_agent: dict):
    resp = await client.patch(f"/api/agents/{test_agent['id']}", json={
        "name": "Updated Bot",
        "temperature": 0.3,
    }, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["agent"]["name"] == "Updated Bot"
    assert resp.json()["agent"]["temperature"] == 0.3


@pytest.mark.asyncio
async def test_delete_agent(client: AsyncClient, auth_headers: dict):
    # Create a separate agent to delete
    resp = await client.post("/api/agents", json={
        "name": "To Delete", "slug": "to-delete",
    }, headers=auth_headers)
    agent_id = resp.json()["agent"]["id"]

    resp = await client.delete(f"/api/agents/{agent_id}", headers=auth_headers)
    assert resp.status_code == 204

    resp = await client.get(f"/api/agents/{agent_id}", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_agent_tenant_isolation(client: AsyncClient, test_agent: dict):
    """Another user cannot see the first user's agent."""
    # Register second user
    resp = await client.post("/api/auth/register", json={
        "email": "other@test.com", "username": "otheruser", "password": "password123",
    })
    other_token = resp.json()["tokens"]["access_token"]
    other_headers = {"Authorization": f"Bearer {other_token}"}

    # Try to access first user's agent
    resp = await client.get(f"/api/agents/{test_agent['id']}", headers=other_headers)
    assert resp.status_code == 404

    # Other user's agent list should be empty
    resp = await client.get("/api/agents", headers=other_headers)
    assert resp.json()["count"] == 0


# ── Conversations API ────────────────────────────────


@pytest.mark.asyncio
async def test_create_conversation(client: AsyncClient, auth_headers: dict):
    resp = await client.post("/api/conversations", json={
        "title": "Test Chat",
    }, headers=auth_headers)
    assert resp.status_code == 201
    assert resp.json()["conversation"]["title"] == "Test Chat"


@pytest.mark.asyncio
async def test_list_conversations(client: AsyncClient, auth_headers: dict):
    await client.post("/api/conversations", json={"title": "C1"}, headers=auth_headers)
    await client.post("/api/conversations", json={"title": "C2"}, headers=auth_headers)

    resp = await client.get("/api/conversations", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["count"] >= 2


@pytest.mark.asyncio
async def test_conversation_no_auth(client: AsyncClient):
    resp = await client.get("/api/conversations")
    assert resp.status_code == 401


# ── API Keys API ─────────────────────────────────────


@pytest.mark.asyncio
async def test_create_api_key(client: AsyncClient, auth_headers: dict):
    resp = await client.post("/api/api-keys", json={
        "name": "test-key",
    }, headers=auth_headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["secret"].startswith("ak_")
    assert data["api_key"]["name"] == "test-key"
    assert "message" in data  # Warning about saving the key


@pytest.mark.asyncio
async def test_list_api_keys(client: AsyncClient, auth_headers: dict):
    await client.post("/api/api-keys", json={"name": "k1"}, headers=auth_headers)
    resp = await client.get("/api/api-keys", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["count"] >= 1


@pytest.mark.asyncio
async def test_revoke_api_key(client: AsyncClient, auth_headers: dict):
    create_resp = await client.post("/api/api-keys", json={"name": "revoke-me"}, headers=auth_headers)
    key_id = create_resp.json()["api_key"]["id"]

    resp = await client.delete(f"/api/api-keys/{key_id}", headers=auth_headers)
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_api_key_auth_for_agent_api(client: AsyncClient, auth_headers: dict, test_agent: dict):
    """Create an API key and use it to access the agent API."""
    # Create key
    key_resp = await client.post("/api/api-keys", json={"name": "agent-key"}, headers=auth_headers)
    api_key = key_resp.json()["secret"]

    # Use key for agent API (will fail at LLM call but should auth OK)
    resp = await client.post(
        f"/api/v1/agents/{test_agent['id']}/messages",
        json={"message": "Hello"},
        headers={"Authorization": f"Bearer {api_key}"},
    )
    # May be 200 (if LLM responds) or 500 (no LLM configured) — but NOT 401
    assert resp.status_code != 401


@pytest.mark.asyncio
async def test_agent_api_invalid_key(client: AsyncClient, test_agent: dict):
    resp = await client.post(
        f"/api/v1/agents/{test_agent['id']}/messages",
        json={"message": "Hello"},
        headers={"Authorization": "Bearer ak_invalidkey"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_agent_api_no_key(client: AsyncClient, test_agent: dict):
    resp = await client.post(
        f"/api/v1/agents/{test_agent['id']}/messages",
        json={"message": "Hello"},
    )
    assert resp.status_code == 401


# ── Health API ───────────────────────────────────────


@pytest.mark.asyncio
async def test_health(client: AsyncClient):
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
