"""Conversation routes — CRUD with tenant isolation."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status

from ...auth.dependencies import get_current_user
from ...auth.models import User
from ...storage.repositories.conversations import (
    ConversationCreate,
    ConversationUpdate,
)
from ...utils.errors import ConversationNotFoundError
from ...utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("")
async def list_conversations(
    request: Request,
    user: User = Depends(get_current_user),
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    """List conversations for the current user."""
    repos = request.app.state.repositories
    conversations = await repos.conversations.list_all(
        limit=limit, offset=offset, user_id=user.id,
    )
    return {
        "conversations": [c.model_dump() for c in conversations],
        "count": len(conversations),
    }


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_conversation(
    data: ConversationCreate,
    request: Request,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Create a new conversation."""
    # Ensure the conversation is owned by the current user
    data.user_id = user.id

    repos = request.app.state.repositories
    conv = await repos.conversations.create(data)
    return {"conversation": conv.model_dump()}


@router.get("/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    request: Request,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Get a specific conversation."""
    repos = request.app.state.repositories
    try:
        conv = await repos.conversations.get(conversation_id)
    except ConversationNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    # Tenant isolation: ensure the user owns this conversation
    if conv.user_id and conv.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    return {"conversation": conv.model_dump()}


@router.patch("/{conversation_id}")
async def update_conversation(
    conversation_id: str,
    data: ConversationUpdate,
    request: Request,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Update a conversation."""
    repos = request.app.state.repositories
    try:
        conv = await repos.conversations.get(conversation_id)
    except ConversationNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    if conv.user_id and conv.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    updated = await repos.conversations.update(conversation_id, data)
    return {"conversation": updated.model_dump()}


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: str,
    request: Request,
    user: User = Depends(get_current_user),
) -> None:
    """Delete a conversation."""
    repos = request.app.state.repositories
    try:
        conv = await repos.conversations.get(conversation_id)
    except ConversationNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    if conv.user_id and conv.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    await repos.conversations.delete(conversation_id)


@router.delete("/{conversation_id}/messages/after/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_messages_after(
    conversation_id: str,
    message_id: str,
    request: Request,
    user: User = Depends(get_current_user),
) -> None:
    """Delete all messages after (not including) a given message. Used for resend/edit."""
    repos = request.app.state.repositories
    try:
        conv = await repos.conversations.get(conversation_id)
    except ConversationNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    if conv.user_id and conv.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    msg = await repos.messages.get(message_id)
    if not msg:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")

    await repos.messages.delete_from(conversation_id, msg.created_at)


@router.get("/{conversation_id}/messages")
async def list_messages(
    conversation_id: str,
    request: Request,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """List messages in a conversation."""
    repos = request.app.state.repositories

    # Verify ownership
    try:
        conv = await repos.conversations.get(conversation_id)
    except ConversationNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    if conv.user_id and conv.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    messages = await repos.messages.get_by_conversation(conversation_id)
    return {
        "messages": [m.model_dump() for m in messages],
        "count": len(messages),
    }
