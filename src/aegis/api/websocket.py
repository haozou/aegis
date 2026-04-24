"""WebSocket endpoint for agent chat with streaming."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..auth.jwt import decode_token
from ..core.types import AgentConfig, StreamEventType
from ..storage.repositories.agents import Agent
from ..storage.repositories.conversations import ConversationCreate
from ..tools.mcp_tool import start_mcp_servers, stop_mcp_servers
from ..tools.registry import ToolRegistry
from ..utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()

# ── Global stream state ──────────────────────────────
_stream_buffers: dict[str, list[dict[str, Any]]] = {}
_stream_tasks: dict[str, asyncio.Task[None]] = {}


def _agent_to_config(agent: Agent, user_id: str = "") -> AgentConfig:
    return AgentConfig(
        provider=agent.provider, model=agent.model,
        temperature=agent.temperature, max_tokens=agent.max_tokens,
        system_prompt=agent.system_prompt,
        enable_memory=agent.enable_memory, enable_skills=agent.enable_skills,
        tool_names=agent.allowed_tools if agent.allowed_tools else None,
        max_tool_iterations=agent.max_tool_iterations,
        agent_id=agent.id, user_id=user_id,
    )


async def _safe_send(ws: WebSocket, data: dict[str, Any]) -> bool:
    """Send JSON to WebSocket, return False if disconnected."""
    try:
        await ws.send_json(data)
        return True
    except Exception:
        return False


async def _safe_receive(ws: WebSocket) -> dict[str, Any] | None:
    """Receive JSON from WebSocket, return None if disconnected."""
    try:
        return await ws.receive_json()
    except Exception:
        return None


@router.websocket("/ws/agents/{agent_id}/chat")
async def agent_chat_ws(websocket: WebSocket, agent_id: str) -> None:
    await websocket.accept()

    app = websocket.app
    jwt_secret: str = app.state.jwt_secret
    repos = app.state.repositories

    user_id: str | None = None
    agent: Agent | None = None
    stream_task_running = False

    try:
        # Auth
        auth_msg = await _safe_receive(websocket)
        if not auth_msg or auth_msg.get("type") != "auth" or not auth_msg.get("token"):
            await _safe_send(websocket, {"type": "error", "error": "Expected auth message"})
            return

        try:
            payload = decode_token(auth_msg["token"], jwt_secret)
            if payload.get("type") != "access":
                raise ValueError("Not an access token")
            user_id = payload["sub"]
        except Exception as e:
            await _safe_send(websocket, {"type": "error", "error": f"Auth failed: {e}"})
            return

        agent = await repos.agents.get(agent_id)
        if agent is None or agent.user_id != user_id:
            await _safe_send(websocket, {"type": "error", "error": "Agent not found"})
            return
        if agent.status != "active":
            await _safe_send(websocket, {"type": "error", "error": f"Agent is {agent.status}"})
            return

        await _safe_send(websocket, {"type": "auth_ok", "user_id": user_id, "agent_id": agent_id})

        # Setup MCP + tools
        config = _agent_to_config(agent, user_id=user_id)
        session_registry = ToolRegistry()
        for tool_name in app.state.tool_registry.list_tools():
            tool = app.state.tool_registry.get(tool_name)
            if tool:
                session_registry.register(tool)

        mcp_configs = agent.metadata.get("mcp_servers", [])
        mcp_clients = []
        if mcp_configs:
            logger.info("Starting MCP servers", agent_id=agent_id, count=len(mcp_configs))

            async def on_mcp_auth_url(server_id: str, message: str) -> None:
                await _safe_send(websocket, {
                    "type": "mcp_auth_required", "server_id": server_id, "message": message,
                })

            mcp_clients = await start_mcp_servers(
                mcp_configs, session_registry, on_auth_url=on_mcp_auth_url
            )

        all_mcp_tools = [t for t in session_registry.list_tools() if t.startswith("mcp__")]
        if config.tool_names is not None:
            config = AgentConfig(
                **{**config.model_dump(), "tool_names": config.tool_names + all_mcp_tools}
            )

        from ..core.orchestrator import AgentOrchestrator
        session_orchestrator = AgentOrchestrator(
            db=app.state.db, repositories=repos, tool_registry=session_registry,
            memory_store=getattr(app.state, 'memory_store', None),
        )
        session = session_orchestrator.create_session(config=config)
        logger.info("WebSocket chat started",
                     agent_id=agent_id, user_id=user_id, session_id=session.id,
                     mcp_servers=len(mcp_clients))

        # Message loop
        next_raw: dict[str, Any] | None = None  # For messages received during streaming
        while True:
            # Use queued message if available, otherwise read from socket
            if next_raw is not None:
                raw = next_raw
                next_raw = None
            else:
                raw = await _safe_receive(websocket)
            if raw is None:
                logger.info("Client disconnected",
                            agent_id=agent_id, stream_running=stream_task_running)
                break

            msg_type = raw.get("type")

            if msg_type == "resume":
                conv_id = raw.get("conversation_id", "")
                buf = list(_stream_buffers.get(conv_id, []))
                is_active = conv_id in _stream_tasks and not _stream_tasks[conv_id].done()

                logger.info("Resume request", conversation_id=conv_id,
                            buffered=len(buf), active=is_active)

                if buf or is_active:
                    # Replay buffered events
                    for evt in buf:
                        if not await _safe_send(websocket, evt):
                            break

                    # Stream new events as they arrive
                    if is_active:
                        sent = len(buf)
                        while conv_id in _stream_tasks and not _stream_tasks[conv_id].done():
                            await asyncio.sleep(0.05)
                            cur = _stream_buffers.get(conv_id, [])
                            while sent < len(cur):
                                if not await _safe_send(websocket, cur[sent]):
                                    break
                                sent += 1
                        # Final flush
                        cur = _stream_buffers.get(conv_id, [])
                        while sent < len(cur):
                            if not await _safe_send(websocket, cur[sent]):
                                break
                            sent += 1
                else:
                    await _safe_send(websocket, {
                        "type": "no_active_stream", "conversation_id": conv_id,
                    })

            elif msg_type == "message":
                content = raw.get("content", "").strip()
                attachments: list[dict[str, str]] = raw.get("attachments", [])
                is_resend = bool(raw.get("resend", False))
                if not content and not attachments:
                    continue
                logger.info("WS message received", is_resend=is_resend, has_conv=bool(raw.get("conversation_id")))

                conversation_id = raw.get("conversation_id")
                if not conversation_id:
                    title = content[:50] + ("..." if len(content) > 50 else "") if content else (
                        attachments[0].get("filename", "File") if attachments else "New conversation"
                    )
                    conv = await repos.conversations.create(ConversationCreate(
                        title=title,
                        provider=agent.provider, model=agent.model,
                        system_prompt=agent.system_prompt,
                        user_id=user_id, agent_id=agent_id,
                    ))
                    conversation_id = conv.id
                    if not await _safe_send(websocket, {
                        "type": "conversation_created",
                        "conversation_id": conversation_id,
                        "title": conv.title,
                    }):
                        break

                # For resend/edit, update config to skip re-saving the user message
                run_config = config
                if is_resend:
                    run_config = AgentConfig(
                        **{**config.model_dump(), "skip_user_message_save": True}
                    )

                # Run stream as background task
                _stream_buffers[conversation_id] = []
                stream_task_running = True

                async def _run(cid: str, msg: str, cfg: AgentConfig,
                               orch: AgentOrchestrator, sid: str,
                               ws: WebSocket, aid: str,
                               atts: list[dict[str, str]]) -> None:
                    nonlocal stream_task_running
                    try:
                        full_resp = ""
                        async for event in orch.send_message(
                            session_id=sid, conversation_id=cid,
                            content=msg, config=cfg, attachments=atts,
                        ):
                            ed = event.to_ws_dict()
                            if cid in _stream_buffers:
                                _stream_buffers[cid].append(ed)
                            await _safe_send(ws, ed)

                            if event.type == StreamEventType.TEXT_DELTA and event.text:
                                full_resp += event.text
                            elif event.type == StreamEventType.DONE and full_resp:
                                disp = getattr(app.state, 'webhook_dispatcher', None)
                                if disp:
                                    await disp.dispatch(
                                        agent_id=aid, event="agent.response",
                                        payload={
                                            "response": full_resp,
                                            "conversation_id": cid,
                                            "message_id": event.message_id,
                                            "usage": event.usage,
                                        },
                                    )
                    except Exception as e:
                        logger.error("Stream error", conversation_id=cid, error=str(e))
                        err_evt = {"type": "error", "error": str(e)}
                        if cid in _stream_buffers:
                            _stream_buffers[cid].append(err_evt)
                        await _safe_send(ws, err_evt)
                    finally:
                        stream_task_running = False
                        # NOTE: buffer cleanup happens separately below so the task
                        # finishes immediately and doesn't block the message loop.

                async def _cleanup_buffer(cid: str) -> None:
                    """Clean up stream buffer after a delay (for reconnection support)."""
                    await asyncio.sleep(60)
                    _stream_buffers.pop(cid, None)
                    _stream_tasks.pop(cid, None)

                task = asyncio.create_task(_run(
                    conversation_id, content, run_config,
                    session_orchestrator, session.id,
                    websocket, agent_id, attachments,
                ))
                _stream_tasks[conversation_id] = task

                # Wait for completion or disconnect
                while not task.done():
                    msg2 = await _safe_receive(websocket)
                    if msg2 is None:
                        # Disconnected — task keeps running
                        logger.info("Disconnected mid-stream, task continues in background",
                                    conversation_id=conversation_id)
                        break
                    if msg2.get("type") == "cancel":
                        session_orchestrator.cancel_session(session.id)
                    elif msg2.get("type") == "ping":
                        await _safe_send(websocket, {"type": "pong"})
                    else:
                        # Got another message (e.g. next user message) — queue it
                        next_raw = msg2
                        logger.info("Queued message during stream",
                                    type=msg2.get("type"),
                                    conversation_id=conversation_id)
                        break  # Exit inner loop, task continues in background
                else:
                    # Task completed normally — schedule buffer cleanup and continue
                    stream_task_running = False
                    asyncio.create_task(_cleanup_buffer(conversation_id))
                    continue

                if next_raw is not None:
                    # We have a queued message — wait for current task to finish first
                    try:
                        await asyncio.wait_for(task, timeout=30.0)
                    except asyncio.TimeoutError:
                        logger.warning("Stream task still running after 30s, processing queued message anyway")
                    stream_task_running = False
                    asyncio.create_task(_cleanup_buffer(conversation_id))
                    continue  # Process queued message in next iteration

                # Broke out of while (disconnect) — exit main loop
                break

            elif msg_type == "cancel":
                session_orchestrator.cancel_session(session.id)

            elif msg_type == "ping":
                await _safe_send(websocket, {"type": "pong"})

        # Cleanup — only if no background task running
        if not stream_task_running:
            session_orchestrator.close_session(session.id)
            await stop_mcp_servers(mcp_clients)
        else:
            logger.info("Keeping session alive for background stream")

    except Exception as e:
        logger.error("WebSocket error", agent_id=agent_id, error=str(e))
        await _safe_send(websocket, {"type": "error", "error": str(e)})
