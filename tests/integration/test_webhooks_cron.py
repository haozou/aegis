"""Tests for webhooks and scheduled tasks."""

import pytest
import pytest_asyncio
from httpx import AsyncClient


# ── Webhook CRUD ─────────────────────────────────────


@pytest.mark.asyncio
async def test_create_inbound_webhook(client: AsyncClient, auth_headers: dict, test_agent: dict):
    resp = await client.post(
        f"/api/agents/{test_agent['id']}/webhooks",
        json={"name": "My Hook", "direction": "inbound"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["webhook"]["direction"] == "inbound"
    assert data["webhook"]["slug"]
    assert data["trigger_url"]
    assert "/api/hooks/" in data["trigger_url"]


@pytest.mark.asyncio
async def test_create_outbound_webhook(client: AsyncClient, auth_headers: dict, test_agent: dict):
    resp = await client.post(
        f"/api/agents/{test_agent['id']}/webhooks",
        json={
            "name": "Notify",
            "direction": "outbound",
            "url": "https://example.com/callback",
            "events": ["agent.response"],
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    wh = resp.json()["webhook"]
    assert wh["direction"] == "outbound"
    assert wh["url"] == "https://example.com/callback"
    assert wh["events"] == ["agent.response"]


@pytest.mark.asyncio
async def test_outbound_webhook_requires_url(client: AsyncClient, auth_headers: dict, test_agent: dict):
    resp = await client.post(
        f"/api/agents/{test_agent['id']}/webhooks",
        json={"name": "Bad", "direction": "outbound"},
        headers=auth_headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_list_webhooks(client: AsyncClient, auth_headers: dict, test_agent: dict):
    await client.post(
        f"/api/agents/{test_agent['id']}/webhooks",
        json={"name": "Hook1"},
        headers=auth_headers,
    )
    resp = await client.get(
        f"/api/agents/{test_agent['id']}/webhooks",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["count"] >= 1


@pytest.mark.asyncio
async def test_delete_webhook(client: AsyncClient, auth_headers: dict, test_agent: dict):
    create_resp = await client.post(
        f"/api/agents/{test_agent['id']}/webhooks",
        json={"name": "Delete Me"},
        headers=auth_headers,
    )
    wh_id = create_resp.json()["webhook"]["id"]

    resp = await client.delete(
        f"/api/agents/{test_agent['id']}/webhooks/{wh_id}",
        headers=auth_headers,
    )
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_inbound_webhook_trigger(client: AsyncClient, auth_headers: dict, test_agent: dict):
    """Create a webhook and POST to its trigger URL."""
    create_resp = await client.post(
        f"/api/agents/{test_agent['id']}/webhooks",
        json={"name": "Trigger Test", "direction": "inbound"},
        headers=auth_headers,
    )
    slug = create_resp.json()["webhook"]["slug"]

    # Trigger the webhook (will try to call LLM — may fail without provider, but should not 404)
    resp = await client.post(
        f"/api/hooks/{slug}",
        json={"message": "Hello from webhook"},
    )
    # Either 200 (LLM responded) or 500 (no LLM) — but not 404
    assert resp.status_code != 404


@pytest.mark.asyncio
async def test_inbound_webhook_not_found(client: AsyncClient):
    resp = await client.post("/api/hooks/nonexistent-slug", json={"message": "hi"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_webhook_deliveries(client: AsyncClient, auth_headers: dict, test_agent: dict):
    create_resp = await client.post(
        f"/api/agents/{test_agent['id']}/webhooks",
        json={"name": "Delivery Test"},
        headers=auth_headers,
    )
    wh_id = create_resp.json()["webhook"]["id"]

    resp = await client.get(
        f"/api/agents/{test_agent['id']}/webhooks/{wh_id}/deliveries",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert "deliveries" in resp.json()


# ── Scheduled Tasks CRUD ─────────────────────────────


@pytest.mark.asyncio
async def test_create_schedule(client: AsyncClient, auth_headers: dict, test_agent: dict):
    resp = await client.post(
        f"/api/agents/{test_agent['id']}/schedules",
        json={
            "name": "Morning Report",
            "cron_expr": "0 9 * * *",
            "prompt": "Give me a summary of today's news.",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    sched = resp.json()["schedule"]
    assert sched["cron_expr"] == "0 9 * * *"
    assert sched["prompt"] == "Give me a summary of today's news."
    assert sched["next_run"] is not None
    assert sched["is_active"] is True


@pytest.mark.asyncio
async def test_create_schedule_invalid_cron(client: AsyncClient, auth_headers: dict, test_agent: dict):
    resp = await client.post(
        f"/api/agents/{test_agent['id']}/schedules",
        json={"cron_expr": "not a cron", "prompt": "Hi"},
        headers=auth_headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_list_schedules(client: AsyncClient, auth_headers: dict, test_agent: dict):
    await client.post(
        f"/api/agents/{test_agent['id']}/schedules",
        json={"cron_expr": "*/5 * * * *", "prompt": "Check status"},
        headers=auth_headers,
    )
    resp = await client.get(
        f"/api/agents/{test_agent['id']}/schedules",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["count"] >= 1


@pytest.mark.asyncio
async def test_delete_schedule(client: AsyncClient, auth_headers: dict, test_agent: dict):
    create_resp = await client.post(
        f"/api/agents/{test_agent['id']}/schedules",
        json={"cron_expr": "0 0 * * *", "prompt": "Midnight task"},
        headers=auth_headers,
    )
    task_id = create_resp.json()["schedule"]["id"]

    resp = await client.delete(
        f"/api/agents/{test_agent['id']}/schedules/{task_id}",
        headers=auth_headers,
    )
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_toggle_schedule(client: AsyncClient, auth_headers: dict, test_agent: dict):
    create_resp = await client.post(
        f"/api/agents/{test_agent['id']}/schedules",
        json={"cron_expr": "0 12 * * *", "prompt": "Noon task"},
        headers=auth_headers,
    )
    task_id = create_resp.json()["schedule"]["id"]

    # Disable
    resp = await client.patch(
        f"/api/agents/{test_agent['id']}/schedules/{task_id}",
        json={"is_active": False},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["schedule"]["is_active"] is False


@pytest.mark.asyncio
async def test_list_schedule_runs(client: AsyncClient, auth_headers: dict, test_agent: dict):
    create_resp = await client.post(
        f"/api/agents/{test_agent['id']}/schedules",
        json={"cron_expr": "0 6 * * *", "prompt": "Early bird"},
        headers=auth_headers,
    )
    task_id = create_resp.json()["schedule"]["id"]

    resp = await client.get(
        f"/api/agents/{test_agent['id']}/schedules/{task_id}/runs",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert "runs" in resp.json()


# ── Repository-level tests ───────────────────────────


@pytest.mark.asyncio
async def test_webhook_repo_crud(repos):
    from aegis.storage.repositories.webhooks import WebhookCreate

    user = await repos.users.create(
        email="whuser@test.com", username="whuser", password_hash="h",
    )
    from aegis.storage.repositories.agents import AgentCreate
    agent = await repos.agents.create(AgentCreate(
        user_id=user.id, name="WHBot", slug="whbot",
    ))

    wh = await repos.webhooks.create(WebhookCreate(
        agent_id=agent.id, user_id=user.id, name="test",
    ))
    assert wh.id.startswith("wh_")
    assert wh.slug.startswith("hook_")

    found = await repos.webhooks.get_by_slug(wh.slug)
    assert found is not None
    assert found.id == wh.id

    webhooks = await repos.webhooks.list_by_agent(agent.id)
    assert len(webhooks) == 1

    assert await repos.webhooks.delete(wh.id) is True
    assert await repos.webhooks.get(wh.id) is None


@pytest.mark.asyncio
async def test_scheduled_task_repo_crud(repos):
    from aegis.storage.repositories.scheduled_tasks import ScheduledTaskCreate
    from aegis.storage.repositories.agents import AgentCreate

    user = await repos.users.create(
        email="cronuser@test.com", username="cronuser", password_hash="h",
    )
    agent = await repos.agents.create(AgentCreate(
        user_id=user.id, name="CronBot", slug="cronbot",
    ))

    task = await repos.scheduled_tasks.create(ScheduledTaskCreate(
        agent_id=agent.id, user_id=user.id,
        name="Daily", cron_expr="0 9 * * *", prompt="Hello",
    ))
    assert task.id.startswith("task_")
    assert task.next_run is not None
    assert task.is_active is True

    tasks = await repos.scheduled_tasks.list_by_agent(agent.id)
    assert len(tasks) == 1

    # Log a run
    run = await repos.scheduled_tasks.log_run(task.id, status="running")
    assert run.id.startswith("run_")

    await repos.scheduled_tasks.complete_run(run.id, "completed", response="Done", tokens_used=10)
    runs = await repos.scheduled_tasks.list_runs(task.id)
    assert len(runs) == 1
    assert runs[0].status == "completed"

    assert await repos.scheduled_tasks.delete(task.id) is True
