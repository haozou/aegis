"""Conversation title generation."""

from __future__ import annotations

from ..utils.logging import get_logger

logger = get_logger(__name__)

TITLE_SYSTEM_PROMPT = """Generate a concise 4-6 word title for this conversation.
Rules:
- 4-6 words maximum
- No quotes, no punctuation at end
- Capture the main topic
- Be specific, not generic
Respond with ONLY the title, nothing else."""


async def generate_title(
    first_message: str,
    provider_name: str | None = None,
    model: str | None = None,
) -> str:
    """Generate a short title for a conversation based on the first message."""
    try:
        from ..llm.registry import get_provider
        from ..llm.types import LLMMessage, LLMRequest

        provider = get_provider(provider_name)
        title_model = model or provider.get_default_model()

        truncated = first_message[:500]
        request = LLMRequest(
            messages=[LLMMessage(role="user", content=truncated)],
            model=title_model,
            system_prompt=TITLE_SYSTEM_PROMPT,
            max_tokens=20,
            temperature=0.3,
        )
        response = await provider.complete(request)
        title = response.content.strip().strip('"\' ').strip()
        if title:
            return title[:80]  # Cap length
    except Exception as e:
        logger.warning("Title generation failed", error=str(e))

    # Fallback: truncate the message
    words = first_message.split()[:6]
    return " ".join(words)[:80] or "New Conversation"
