"""ID generation utilities."""

from __future__ import annotations

import uuid


def new_id(prefix: str) -> str:
    """Generate a prefixed UUID4 ID."""
    uid = uuid.uuid4().hex[:12]
    return f"{prefix}_{uid}"


def new_session_id() -> str:
    """Generate a new session ID."""
    return new_id("sess")


def new_message_id() -> str:
    """Generate a new message ID."""
    return new_id("msg")


def new_conversation_id() -> str:
    """Generate a new conversation ID."""
    return new_id("conv")


def new_tool_call_id() -> str:
    """Generate a new tool call ID."""
    return new_id("tc")


def new_memory_id() -> str:
    """Generate a new memory entry ID."""
    return new_id("mem")


def new_user_id() -> str:
    """Generate a new user ID."""
    return new_id("usr")


def new_agent_id() -> str:
    """Generate a new agent ID."""
    return new_id("agt")


def new_api_key_id() -> str:
    """Generate a new API key ID."""
    return new_id("ak")
