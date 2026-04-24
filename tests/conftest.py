"""Shared test fixtures."""

from __future__ import annotations

import asyncio
import os
from typing import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Force SQLite for tests
os.environ.pop("DATABASE_URL", None)
os.environ["JWT_SECRET"] = "test-secret-key-that-is-32-chars!!"


@pytest.fixture(scope="session")
def event_loop():
    """Create a single event loop for all tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def db():
    """Create a fresh in-memory-like SQLite database for each test."""
    from aegis.storage.database import Database

    database = Database(db_path=":memory:")
    # aiosqlite doesn't support :memory: well across tasks,
    # so use a temp file instead
    import tempfile
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    database = Database(db_path=tmp.name)
    await database.connect()
    yield database
    await database.close()
    os.unlink(tmp.name)


@pytest_asyncio.fixture
async def repos(db):
    """Create repositories from the test database."""
    from aegis.storage.repositories import get_repositories
    return get_repositories(db)


@pytest_asyncio.fixture
async def app(db, repos):
    """Create a test FastAPI app with fresh database."""
    from aegis.app import create_app
    from aegis.auth.service import AuthService
    from aegis.core.orchestrator import AgentOrchestrator
    from aegis.tools.registry import ToolRegistry
    from aegis.storage.database import set_db_instance

    set_db_instance(db)

    application = create_app()

    # Override app state with test instances
    application.state.db = db
    application.state.repositories = repos
    application.state.jwt_secret = "test-secret-key-that-is-32-chars!!"
    application.state.auth_service = AuthService(
        user_repo=repos.users,
        jwt_secret="test-secret-key-that-is-32-chars!!",
    )

    tool_registry = ToolRegistry()
    tool_registry.register_builtins(
        bash_enabled=False,  # Disable bash in tests for safety
        web_fetch_enabled=False,
        file_ops_enabled=False,
    )
    application.state.tool_registry = tool_registry
    application.state.orchestrator = AgentOrchestrator(
        db=db,
        repositories=repos,
        tool_registry=tool_registry,
    )

    yield application


@pytest_asyncio.fixture
async def client(app) -> AsyncIterator[AsyncClient]:
    """Create an async HTTP client for the test app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def auth_headers(client: AsyncClient) -> dict[str, str]:
    """Register a test user and return auth headers."""
    resp = await client.post("/api/auth/register", json={
        "email": "test@example.com",
        "username": "testuser",
        "password": "testpassword123",
        "display_name": "Test User",
    })
    assert resp.status_code == 201
    token = resp.json()["tokens"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def test_agent(client: AsyncClient, auth_headers: dict[str, str]) -> dict:
    """Create a test agent and return its data."""
    resp = await client.post("/api/agents", json={
        "name": "Test Agent",
        "system_prompt": "You are a test agent.",
        "description": "An agent for testing",
    }, headers=auth_headers)
    assert resp.status_code == 201
    return resp.json()["agent"]
