"""JWT token creation and validation."""

from __future__ import annotations

import time
from typing import Any

import jwt

from ..utils.errors import AuthError, AuthTokenExpiredError
from ..utils.logging import get_logger

logger = get_logger(__name__)

# Defaults
ACCESS_TOKEN_EXPIRE_SECONDS = 3600  # 1 hour
REFRESH_TOKEN_EXPIRE_SECONDS = 604800  # 7 days
ALGORITHM = "HS256"


def create_access_token(
    user_id: str,
    secret: str,
    expires_in: int = ACCESS_TOKEN_EXPIRE_SECONDS,
) -> str:
    """Create a JWT access token."""
    now = int(time.time())
    payload: dict[str, Any] = {
        "sub": user_id,
        "iat": now,
        "exp": now + expires_in,
        "type": "access",
    }
    return jwt.encode(payload, secret, algorithm=ALGORITHM)


def create_refresh_token(
    user_id: str,
    secret: str,
    expires_in: int = REFRESH_TOKEN_EXPIRE_SECONDS,
) -> str:
    """Create a JWT refresh token."""
    now = int(time.time())
    payload: dict[str, Any] = {
        "sub": user_id,
        "iat": now,
        "exp": now + expires_in,
        "type": "refresh",
    }
    return jwt.encode(payload, secret, algorithm=ALGORITHM)


def create_token_pair(
    user_id: str,
    secret: str,
    access_expires_in: int = ACCESS_TOKEN_EXPIRE_SECONDS,
    refresh_expires_in: int = REFRESH_TOKEN_EXPIRE_SECONDS,
) -> dict[str, Any]:
    """Create both access and refresh tokens."""
    return {
        "access_token": create_access_token(user_id, secret, access_expires_in),
        "refresh_token": create_refresh_token(user_id, secret, refresh_expires_in),
        "token_type": "bearer",
        "expires_in": access_expires_in,
    }


def decode_token(token: str, secret: str) -> dict[str, Any]:
    """Decode and validate a JWT token.

    Returns the decoded payload dict.
    Raises AuthTokenExpiredError if expired, AuthError for other issues.
    """
    try:
        payload: dict[str, Any] = jwt.decode(token, secret, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise AuthTokenExpiredError("Token has expired")
    except jwt.InvalidTokenError as e:
        raise AuthError(f"Invalid token: {e}")
