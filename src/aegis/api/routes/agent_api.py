"""Public agent API — send messages using API keys."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from ...core.types import AgentConfig, StreamEventType
from ...storage.repositories.agents import Agent
from ...storage.repositories.conversations import ConversationCreate
from ...utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/v1", tags=["agent-api"])


class SendMessageRequest(BaseModel):
    message: str
    conversation_id: str | None = None


class MessageResponse(BaseModel):
    conversation_id: str
    message_id: str
    response: str
    usage: dict[str, int]


def _agent_to_config(agent: Agent) -> AgentConfig:
    return AgentConfig(
        provider=agent.provider,
        model=agent.model,
        temperature=agent.temperature,
        max_tokens=agent.max_tokens,
        system_prompt=agent.system_prompt,
        enable_memory=agent.enable_memory,
        enable_skills=agent.enable_skills,
        tool_names=agent.allowed_tools if agent.allowed_tools else None,
        max_tool_iterations=agent.max_tool_iterations,
    )


async def _get_user_from_api_key(request: Request) -> tuple[str, str]:
    """Extract and verify API key from Authorization header.
    Returns (user_id, key_prefix).
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer ak_"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid API key. Use: Authorization: Bearer ak_...",
        )

    full_key = auth_header[7:]  # Strip "Bearer "
    repos = request.app.state.repositories
    api_key = await repos.api_keys.verify(full_key)

    if api_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or revoked API key",
        )

    if "agent:execute" not in api_key.scopes:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API key lacks 'agent:execute' scope",
        )

    return api_key.user_id, api_key.key_prefix


@router.post("/agents/{agent_id}/messages")
async def send_message_via_api(
    agent_id: str,
    data: SendMessageRequest,
    request: Request,
) -> dict[str, Any]:
    """Send a message to an agent and get the full response (non-streaming).

    Authentication: Bearer API key (ak_...)
    """
    user_id, key_prefix = await _get_user_from_api_key(request)

    repos = request.app.state.repositories
    orchestrator = request.app.state.orchestrator

    # Verify agent ownership
    agent = await repos.agents.get(agent_id)
    if agent is None or agent.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    if agent.status != "active":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Agent is {agent.status}")

    # Create or reuse conversation
    conversation_id = data.conversation_id
    if not conversation_id:
        title = data.message[:50] + ("..." if len(data.message) > 50 else "")
        conv = await repos.conversations.create(ConversationCreate(
            title=title,
            provider=agent.provider,
            model=agent.model,
            user_id=user_id,
            agent_id=agent_id,
        ))
        conversation_id = conv.id

    # Run agent
    config = _agent_to_config(agent)
    session = orchestrator.create_session(config=config)

    full_text = ""
    message_id = ""
    usage = {"input": 0, "output": 0}

    try:
        async for event in orchestrator.send_message(
            session_id=session.id,
            conversation_id=conversation_id,
            content=data.message,
            config=config,
        ):
            if event.type == StreamEventType.TEXT_DELTA and event.text:
                full_text += event.text
            elif event.type == StreamEventType.DONE:
                message_id = event.message_id or ""
                usage = event.usage or {"input": 0, "output": 0}
            elif event.type == StreamEventType.ERROR:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=event.error or "Agent error",
                )
    finally:
        orchestrator.close_session(session.id)

    logger.info(
        "API message processed",
        agent_id=agent_id, user_id=user_id, key_prefix=key_prefix,
        tokens=usage.get("input", 0) + usage.get("output", 0),
    )

    # Fire outbound webhooks
    dispatcher = getattr(request.app.state, 'webhook_dispatcher', None)
    if dispatcher and full_text:
        await dispatcher.dispatch(
            agent_id=agent_id,
            event="agent.response",
            payload={
                "response": full_text,
                "conversation_id": conversation_id,
                "message_id": message_id,
                "usage": usage,
            },
        )

    return {
        "conversation_id": conversation_id,
        "message_id": message_id,
        "response": full_text,
        "usage": usage,
    }
