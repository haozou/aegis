"""Ollama provider (delegates to OpenAI-compatible API)."""

from __future__ import annotations

import httpx

from ...utils.logging import get_logger
from .openai import OpenAIProvider

logger = get_logger(__name__)


class OllamaProvider(OpenAIProvider):
    """Ollama provider using OpenAI-compatible /v1 API."""

    name = "ollama"

    def __init__(self, base_url: str = "http://localhost:11434") -> None:
        super().__init__(api_key="ollama", base_url=f"{base_url}/v1")
        self._ollama_base_url = base_url

    def get_default_model(self) -> str:
        return "llama3.2"

    async def list_models(self) -> list[str]:
        """List locally available Ollama models."""
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{self._ollama_base_url}/api/tags", timeout=10.0)
                resp.raise_for_status()
                data = resp.json()
                return [m["name"] for m in data.get("models", [])]
        except Exception as e:
            logger.warning("Failed to list Ollama models", error=str(e))
            return []

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{self._ollama_base_url}/api/tags", timeout=5.0)
                return resp.status_code == 200
        except Exception:
            return False
