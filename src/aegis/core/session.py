"""Agent session management."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from ..utils.ids import new_session_id
from ..utils.logging import get_logger
from .types import AgentConfig

logger = get_logger(__name__)


class AgentSession:
    """Represents an active agent session tied to a WebSocket connection."""

    def __init__(
        self,
        session_id: str | None = None,
        conversation_id: str | None = None,
        config: AgentConfig | None = None,
    ) -> None:
        self.id = session_id or new_session_id()
        self.conversation_id = conversation_id
        self.config = config or AgentConfig()
        self.created_at = datetime.now(timezone.utc)
        self.last_active = self.created_at
        self._cancel_event = asyncio.Event()
        self._streaming = False

    @property
    def is_streaming(self) -> bool:
        return self._streaming

    @property
    def is_cancelled(self) -> bool:
        return self._cancel_event.is_set()

    def request_cancel(self) -> None:
        """Signal the session to cancel the current operation."""
        logger.info("Session cancel requested", session_id=self.id)
        self._cancel_event.set()

    def reset_cancel(self) -> None:
        """Clear the cancel signal for the next operation."""
        self._cancel_event.clear()

    def set_streaming(self, streaming: bool) -> None:
        self._streaming = streaming
        if not streaming:
            self._cancel_event.clear()

    def touch(self) -> None:
        self.last_active = datetime.now(timezone.utc)

    async def wait_for_cancel(self, timeout: float = 0.0) -> bool:
        """Wait for cancel signal. Returns True if cancelled."""
        try:
            await asyncio.wait_for(self._cancel_event.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False
