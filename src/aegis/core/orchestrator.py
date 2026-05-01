"""Agent orchestrator - manages sessions and routes messages."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from ..utils.errors import SessionNotFoundError
from ..utils.ids import new_session_id
from ..utils.logging import get_logger
from .session import AgentSession
from .tool_loop import ToolLoop
from .types import AgentConfig, StreamEvent, StreamEventType

logger = get_logger(__name__)


class AgentOrchestrator:
    """Manages agent sessions and the tool execution loop."""

    def __init__(
        self,
        db: Any,
        repositories: Any,
        tool_registry: Any,
        memory_store: Any | None = None,
        skills_loader: Any | None = None,
    ) -> None:
        self._db = db
        self._repos = repositories
        self._tools = tool_registry
        self._memory = memory_store
        self._skills = skills_loader
        self._sessions: dict[str, AgentSession] = {}
        self._tool_loop = ToolLoop(
            db=db,
            repositories=repositories,
            tool_registry=tool_registry,
            memory_store=memory_store,
            skills_loader=skills_loader,
        )

    def create_session(
        self,
        session_id: str | None = None,
        conversation_id: str | None = None,
        config: AgentConfig | None = None,
    ) -> AgentSession:
        """Create a new agent session."""
        sess = AgentSession(
            session_id=session_id or new_session_id(),
            conversation_id=conversation_id,
            config=config or AgentConfig(),
        )
        self._sessions[sess.id] = sess
        logger.info("Session created", session_id=sess.id, conversation_id=conversation_id)
        return sess

    def get_session(self, session_id: str) -> AgentSession:
        """Get an existing session."""
        sess = self._sessions.get(session_id)
        if sess is None:
            raise SessionNotFoundError(f"Session {session_id!r} not found")
        return sess

    def cancel_session(self, session_id: str) -> None:
        """Request cancellation of a session's current operation."""
        sess = self._sessions.get(session_id)
        if sess:
            sess.request_cancel()

    def close_session(self, session_id: str) -> None:
        """Remove a session."""
        sess = self._sessions.pop(session_id, None)
        if sess:
            sess.request_cancel()
            logger.info("Session closed", session_id=session_id)

    async def send_message(
        self,
        session_id: str,
        conversation_id: str,
        content: str,
        config: AgentConfig | None = None,
        attachments: list[dict[str, str]] | None = None,
        quote: dict[str, str] | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """Send a message and stream the response."""
        sess = self.get_session(session_id)
        sess.reset_cancel()
        sess.set_streaming(True)
        sess.touch()

        effective_config = config or sess.config

        try:
            async for event in self._tool_loop.run(
                session=sess,
                conversation_id=conversation_id,
                user_message=content,
                config=effective_config,
                attachments=attachments or [],
                quote=quote,
            ):
                yield event
        except Exception as e:
            logger.error("Tool loop error", session_id=session_id, error=str(e))
            yield StreamEvent(type=StreamEventType.ERROR, error=str(e))
        finally:
            sess.set_streaming(False)

    @property
    def active_sessions(self) -> int:
        return len(self._sessions)