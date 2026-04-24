"""Authentication routes — register, login, refresh, profile."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from ...auth.dependencies import get_current_user
from ...auth.jwt import decode_token
from ...auth.models import TokenPair, User, UserCreate, UserLogin
from ...utils.errors import AuthError, AuthTokenExpiredError
from ...utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=dict, status_code=status.HTTP_201_CREATED)
async def register(data: UserCreate, request: Request) -> dict:
    """Register a new user account."""
    auth_service = request.app.state.auth_service

    if not request.app.state.settings.auth.allow_registration:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Registration is currently disabled",
        )

    try:
        user, tokens = await auth_service.register(data)
    except AuthError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )

    return {
        "user": user.model_dump(exclude={"metadata"}),
        "tokens": tokens.model_dump(),
    }


@router.post("/login", response_model=dict)
async def login(data: UserLogin, request: Request) -> dict:
    """Authenticate and get access tokens."""
    auth_service = request.app.state.auth_service

    try:
        user, tokens = await auth_service.login(data)
    except AuthError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        )

    return {
        "user": user.model_dump(exclude={"metadata"}),
        "tokens": tokens.model_dump(),
    }


@router.post("/refresh", response_model=dict)
async def refresh_token(request: Request) -> dict:
    """Refresh access token using a refresh token.

    Send the refresh token in the Authorization header as: Bearer <refresh_token>
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing refresh token",
        )

    token = auth_header[7:]
    jwt_secret = request.app.state.jwt_secret

    try:
        payload = decode_token(token, jwt_secret)
    except AuthTokenExpiredError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has expired",
        )
    except AuthError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        )

    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type — expected refresh token",
        )

    auth_service = request.app.state.auth_service
    try:
        tokens = await auth_service.refresh_tokens(payload["sub"])
    except AuthError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        )

    return {"tokens": tokens.model_dump()}


@router.get("/me", response_model=dict)
async def get_me(user: User = Depends(get_current_user)) -> dict:
    """Get the currently authenticated user."""
    return {"user": user.model_dump(exclude={"metadata"})}


class UpdateProfileRequest(BaseModel):
    display_name: str | None = None


@router.patch("/me", response_model=dict)
async def update_me(
    data: UpdateProfileRequest,
    request: Request,
    user: User = Depends(get_current_user),
) -> dict:
    """Update the current user's profile."""
    repos = request.app.state.repositories
    updated = await repos.users.update(
        user.id,
        display_name=data.display_name,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="User not found")
    return {"user": updated.model_dump(exclude={"metadata"})}


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


@router.post("/me/password")
async def change_password(
    data: ChangePasswordRequest,
    request: Request,
    user: User = Depends(get_current_user),
) -> dict:
    """Change the current user's password."""
    from ...auth.passwords import hash_password, verify_password

    repos = request.app.state.repositories

    if len(data.new_password) < 6:
        raise HTTPException(status_code=422, detail="Password must be at least 6 characters")

    # Verify current password
    user_with_hash = await repos.users.get_by_email_with_password(user.email)
    if not user_with_hash:
        raise HTTPException(status_code=404, detail="User not found")
    _, password_hash = user_with_hash

    if not verify_password(data.current_password, password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    # Update password
    new_hash = hash_password(data.new_password)
    await repos.users.update_password(user.id, new_hash)

    return {"message": "Password updated successfully"}
