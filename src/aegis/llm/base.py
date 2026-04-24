"""Base LLM provider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from .types import LLMRequest, LLMResponse, StreamDelta


class BaseLLMProvider(ABC):
    """Abstract base for LLM providers."""

    name: str = "base"

    @abstractmethod
    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Send a completion request and return the full response."""
        ...

    @abstractmethod
    async def stream(self, request: LLMRequest) -> AsyncIterator[StreamDelta]:
        """Stream a completion response as deltas."""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the provider is available."""
        ...

    def get_default_model(self) -> str:
        """Return the default model for this provider."""
        return ""
