"""Models route — returns the list of models available from the configured LLM backend."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from ...auth.dependencies import get_current_user
from ...auth.models import User
from ...llm.registry import get_provider
from ...utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/models", tags=["models"])


@router.get("")
async def list_models_endpoint(
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Return models available from the configured LLM backend."""
    try:
        provider = get_provider()
        if hasattr(provider, "list_models"):
            models = await provider.list_models()
            if models:
                return {"models": models, "default": provider.get_default_model()}
        # Provider has no list_models — return just the default
        default = provider.get_default_model()
        return {"models": [default], "default": default}
    except Exception as e:
        logger.warning("Failed to list models", error=str(e))
        default = "claude-sonnet-4-5"
        return {"models": [default], "default": default}
