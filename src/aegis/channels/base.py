"""Base channel abstraction for Aegis channel adapters."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from ..core.types import AgentConfig, StreamEventType
from ..storage.repositories.conversations import ConversationCreate
from ..utils.ids import new_id
from ..utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class InboundMessage:
    """A message received from an external channel."""

    channel_type: str
    external_user_id: str   # Discord user id, email address, phone number, etc.
    external_chat_id: str   # Discord channel id, email thread id, Telegram chat id, etc.
    text: str
    raw: dict[str, Any] = field(default_factory=dict)


class BaseChannel(ABC):
    """Abstract base for all channel adapters.

    Subclasses implement `start`, `stop`, and `send_reply`.
    The shared `handle_message` method drives the agent execution loop.
    """

    def __init__(
        self,
        connection_id: str,
        agent_id: str,
        user_id: str,
        config: dict[str, Any],
        orchestrator: Any,
        db: Any,
        repos: Any,
    ) -> None:
        self.connection_id = connection_id
        self.agent_id = agent_id
        self.user_id = user_id
        self.config = config
        self._orchestrator = orchestrator
        self._db = db
        self._repos = repos
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    @abstractmethod
    async def start(self) -> None:
        """Connect to the platform and start listening for messages."""

    @abstractmethod
    async def stop(self) -> None:
        """Disconnect from the platform."""

    @abstractmethod
    async def send_reply(self, msg: InboundMessage, reply_text: str) -> None:
        """Send a reply back to the originating platform/user."""

    # ------------------------------------------------------------------ #
    # Shared agent execution — implemented once, used by all adapters     #
    # ------------------------------------------------------------------ #

    async def handle_message(self, msg: InboundMessage) -> None:
        """Route an inbound message through the agent and send the reply."""
        try:
            conversation_id = await self._get_or_create_conversation(msg)
            reply_text = await self._run_agent(conversation_id, msg.text)
            if reply_text:
                await self.send_reply(msg, reply_text)
        except Exception as exc:
            logger.error(
                "Channel handle_message error",
                connection_id=self.connection_id,
                agent_id=self.agent_id,
                channel_type=msg.channel_type,
                error=str(exc),
            )

    async def _get_or_create_conversation(self, msg: InboundMessage) -> str:
        """Find the open conversation for this chat, or create a new one."""
        # Key conversations by external_chat_id stored in metadata
        rows = await self._db.fetchall(
            """SELECT id FROM conversations
               WHERE agent_id = $1
                 AND user_id  = $2
                 AND json_extract(metadata, '$.channel_chat_id') = $3
               ORDER BY updated_at DESC
               LIMIT 1""",
            (self.agent_id, self.user_id, msg.external_chat_id),
        )

        if rows:
            return rows[0]["id"]

        # Fetch agent to get model/provider info
        agent = await self._repos.agents.get(self.agent_id)
        provider = agent.provider if agent else "anthropic"
        model = agent.model if agent else "claude-sonnet-4-5"

        conv = await self._repos.conversations.create(
            ConversationCreate(
                title=f"{msg.channel_type.title()} — {msg.external_user_id[:30]}",
                provider=provider,
                model=model,
                user_id=self.user_id,
                agent_id=self.agent_id,
                metadata={
                    "channel_type": msg.channel_type,
                    "channel_chat_id": msg.external_chat_id,
                    "channel_user_id": msg.external_user_id,
                    "connection_id": self.connection_id,
                },
            )
        )
        return conv.id

    async def _run_agent(self, conversation_id: str, text: str) -> str:
        """Run the agent and collect the full text response."""
        agent = await self._repos.agents.get(self.agent_id)
        if agent is None:
            logger.error("Agent not found", agent_id=self.agent_id)
            return ""

        config = AgentConfig(
            provider=agent.provider,
            model=agent.model,
            temperature=agent.temperature,
            max_tokens=agent.max_tokens,
            system_prompt=agent.system_prompt,
            enable_memory=agent.enable_memory,
            enable_skills=agent.enable_skills,
            tool_names=agent.allowed_tools or None,
            max_tool_iterations=agent.max_tool_iterations,
            agent_id=self.agent_id,
            user_id=self.user_id,
        )

        session_id = new_id("sess")
        session = self._orchestrator.create_session(
            session_id=session_id,
            conversation_id=conversation_id,
            config=config,
        )

        response_parts: list[str] = []
        try:
            async for event in self._orchestrator.send_message(
                session_id=session.id,
                conversation_id=conversation_id,
                content=text,
                config=config,
            ):
                if event.type == StreamEventType.TEXT_DELTA and event.text:
                    response_parts.append(event.text)
        finally:
            self._orchestrator.close_session(session.id)

        return "".join(response_parts)
