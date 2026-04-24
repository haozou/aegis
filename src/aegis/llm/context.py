"""Context window management."""

from __future__ import annotations

from ..utils.tokens import count_tokens
from .types import LLMMessage

MODEL_CONTEXT_WINDOWS: dict[str, int] = {
    # Anthropic
    "claude-opus-4-5": 200000,
    "claude-sonnet-4-5": 200000,
    "claude-haiku-4-5": 200000,
    "claude-3-5-sonnet-20241022": 200000,
    "claude-3-5-haiku-20241022": 200000,
    # OpenAI
    "gpt-4o": 128000,
    "gpt-4o-mini": 128000,
    "gpt-4.1": 1047576,
    "gpt-4.1-mini": 1047576,
    "gpt-4.1-nano": 1047576,
    "gpt-4-turbo": 128000,
    "gpt-3.5-turbo": 16000,
    "gpt-5": 1047576,
    "gpt-5-mini": 1047576,
    # Ollama (typical)
    "llama3.2": 128000,
    "llama3.1": 128000,
    "mistral": 32000,
    "mixtral": 32000,
    "phi3": 128000,
    "gemma2": 8192,
}

DEFAULT_CONTEXT_WINDOW = 128000
RESERVED_OUTPUT_TOKENS = 4096


def get_context_window(model: str) -> int:
    """Get context window size for a model."""
    # Exact match
    if model in MODEL_CONTEXT_WINDOWS:
        return MODEL_CONTEXT_WINDOWS[model]
    # Prefix match
    for known_model, size in MODEL_CONTEXT_WINDOWS.items():
        if model.startswith(known_model) or known_model.startswith(model.split(":")[0]):
            return size
    return DEFAULT_CONTEXT_WINDOW


def estimate_message_tokens(msg: LLMMessage) -> int:
    """Estimate tokens for a message."""
    content = msg.content
    if isinstance(content, str):
        return count_tokens(content) + 4  # role overhead
    elif isinstance(content, list):
        total = 4
        for part in content:
            if isinstance(part, dict):
                if part.get("type") == "text":
                    total += count_tokens(str(part.get("text", "")))
                else:
                    total += count_tokens(str(part))
        return total
    return 4


def prune_messages(
    messages: list[LLMMessage],
    model: str,
    system_prompt: str = "",
    max_tokens: int | None = None,
) -> list[LLMMessage]:
    """Trim message history to fit within the context window.

    Strategy: keep system + first user message + as many recent messages as fit.
    """
    context_window = max_tokens or get_context_window(model)
    available = context_window - RESERVED_OUTPUT_TOKENS

    if system_prompt:
        available -= count_tokens(system_prompt) + 10

    if not messages:
        return messages

    # Separate system messages and other messages
    system_msgs = [m for m in messages if m.role == "system"]
    non_system = [m for m in messages if m.role != "system"]

    for m in system_msgs:
        available -= estimate_message_tokens(m)

    if available <= 0:
        return non_system[-1:] if non_system else []

    # Always try to keep first user message for context
    first_user = None
    rest = non_system
    if non_system and non_system[0].role == "user":
        first_user = non_system[0]
        rest = non_system[1:]
        available -= estimate_message_tokens(first_user)

    # Fit as many recent messages as possible
    kept = []
    for msg in reversed(rest):
        tokens = estimate_message_tokens(msg)
        if available - tokens >= 0:
            kept.insert(0, msg)
            available -= tokens
        else:
            break  # Stop if we can't fit more

    result = []
    if first_user:
        result.append(first_user)
    result.extend(kept)
    return result
