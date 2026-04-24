"""LLM provider registry."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..utils.errors import ConfigError, LLMError
from ..utils.logging import get_logger

if TYPE_CHECKING:
    from .base import BaseLLMProvider

logger = get_logger(__name__)

_providers: dict[str, "BaseLLMProvider"] = {}


def register_provider(name: str, provider: "BaseLLMProvider") -> None:
    _providers[name] = provider


def get_provider(name: str | None = None) -> "BaseLLMProvider":
    """Return the best available provider.

    Resolution order:
    1. LiteLLM proxy — always preferred when registered (it routes everything)
    2. The explicitly named provider (if given and registered)
    3. The first registered provider
    """
    # LiteLLM always wins — it's the universal router
    if "litellm" in _providers:
        return _providers["litellm"]
    # Named lookup
    if name and name in _providers:
        return _providers[name]
    # Any registered provider
    if _providers:
        return next(iter(_providers.values()))
    raise ConfigError(
        f"No LLM provider registered. "
        f"Set LITELLM_BASE_URL (recommended) or ANTHROPIC_API_KEY / OPENAI_API_KEY in .env"
    )


def get_default_provider() -> "BaseLLMProvider":
    """Convenience alias — always returns the active provider."""
    return get_provider()


def list_providers() -> list[str]:
    return list(_providers.keys())


def initialize_providers(
    anthropic_api_key: str = "",
    anthropic_base_url: str = "",
    openai_api_key: str = "",
    openai_base_url: str = "",
    litellm_base_url: str = "",
    ollama_base_url: str = "http://localhost:11434",
) -> None:
    """Initialize LLM providers from config.

    When ``litellm_base_url`` is set it is registered as the sole provider —
    individual native providers are NOT registered alongside it, avoiding any
    ambiguity about which provider handles a request.

    Without LiteLLM, individual native providers are registered based on
    whichever API keys / base URLs are present.
    """
    global _providers
    _providers = {}  # reset on every call (safe for testing / hot-reload)

    if litellm_base_url:
        from .providers.litellm_proxy import LiteLLMProxyProvider
        proxy = LiteLLMProxyProvider(base_url=litellm_base_url)
        register_provider("litellm", proxy)
        logger.info("LLM backend: LiteLLM proxy", base_url=litellm_base_url)
        return

    # ── Native providers (only when LiteLLM is not configured) ──────────────
    registered: list[str] = []

    if anthropic_api_key or anthropic_base_url:
        from .providers.anthropic import AnthropicProvider
        register_provider(
            "anthropic",
            AnthropicProvider(api_key=anthropic_api_key, base_url=anthropic_base_url),
        )
        registered.append("anthropic")

    if openai_api_key or openai_base_url:
        from .providers.openai import OpenAIProvider
        register_provider(
            "openai",
            OpenAIProvider(api_key=openai_api_key or "dummy", base_url=openai_base_url or None),
        )
        registered.append("openai")

    from .providers.ollama import OllamaProvider
    register_provider("ollama", OllamaProvider(base_url=ollama_base_url))
    registered.append("ollama")

    if registered:
        logger.info("LLM backend: native providers", providers=registered)
    else:
        logger.warning("No LLM provider configured — set LITELLM_BASE_URL or an API key")


async def check_all_providers() -> dict[str, bool]:
    """Health-check all registered providers."""
    results: dict[str, bool] = {}
    for name, provider in _providers.items():
        try:
            results[name] = await provider.health_check()
        except Exception:
            results[name] = False
    return results
