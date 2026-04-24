"""Auth data models."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, EmailStr, Field


class UserCreate(BaseModel):
    """Request body for user registration."""
    email: str
    username: str = Field(min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_-]+$")
    password: str = Field(min_length=8, max_length=128)
    display_name: str | None = None


class UserLogin(BaseModel):
    """Request body for user login."""
    email: str
    password: str


class User(BaseModel):
    """User model returned from the database."""
    id: str
    email: str
    username: str
    display_name: str | None = None
    avatar_url: str | None = None
    plan: str = "free"
    is_active: bool = True
    is_admin: bool = False
    created_at: str
    updated_at: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class TokenPair(BaseModel):
    """JWT token pair returned on login/register."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class TokenPayload(BaseModel):
    """Decoded JWT payload."""
    sub: str  # user_id
    exp: int
    iat: int
    type: str  # "access" or "refresh"
