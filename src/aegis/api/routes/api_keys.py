"""API key routes — create, list, revoke."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from ...auth.dependencies import get_current_user
from ...auth.models import User
from ...utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api-keys", tags=["api-keys"])


class CreateApiKeyRequest(BaseModel):
    name: str = "default"


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_api_key(
    data: CreateApiKeyRequest,
    request: Request,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Create a new API key. The full key is only shown once."""
    repos = request.app.state.repositories
    result = await repos.api_keys.create(user_id=user.id, name=data.name)

    logger.info("API key created", user_id=user.id, key_prefix=result.api_key.key_prefix)
    return {
        "api_key": result.api_key.model_dump(),
        "secret": result.secret,
        "message": "Save this key — it will not be shown again.",
    }


@router.get("")
async def list_api_keys(
    request: Request,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """List all active API keys for the current user."""
    repos = request.app.state.repositories
    keys = await repos.api_keys.list_by_user(user.id)
    return {
        "api_keys": [k.model_dump() for k in keys],
        "count": len(keys),
    }


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(
    key_id: str,
    request: Request,
    user: User = Depends(get_current_user),
) -> None:
    """Revoke an API key."""
    repos = request.app.state.repositories
    revoked = await repos.api_keys.revoke(key_id, user.id)
    if not revoked:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found",
        )
    logger.info("API key revoked", key_id=key_id, user_id=user.id)
