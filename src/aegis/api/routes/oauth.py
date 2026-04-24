"""OAuth login routes — Google, GitHub, Microsoft.

Server-side redirect flow:
  1. GET  /auth/oauth/{provider}/start    — redirects to provider
  2. GET  /auth/oauth/{provider}/callback — exchanges code, issues JWTs, redirects to frontend
"""

from __future__ import annotations

from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import RedirectResponse

from ...auth.oauth import (
    build_providers,
    exchange_code_and_fetch_user,
    generate_state,
    get_authorize_url,
)
from ...utils.errors import AuthError
from ...utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/auth/oauth", tags=["oauth"])

STATE_COOKIE = "aegis_oauth_state"
STATE_COOKIE_MAX_AGE = 600  # 10 minutes


def _redirect_uri(request: Request, provider_name: str) -> str:
    base = request.app.state.settings.oauth.redirect_base.rstrip("/")
    return f"{base}/api/auth/oauth/{provider_name}/callback"


def _frontend_base(request: Request) -> str:
    return request.app.state.settings.oauth.redirect_base.rstrip("/")


@router.get("/{provider_name}/start")
async def oauth_start(provider_name: str, request: Request) -> RedirectResponse:
    """Start an OAuth flow — redirect user to the provider's authorize page."""
    oauth_config = request.app.state.settings.oauth
    providers = build_providers(oauth_config)
    provider = providers.get(provider_name)
    if provider is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"OAuth provider '{provider_name}' is not configured",
        )

    state = generate_state()
    redirect_uri = _redirect_uri(request, provider_name)
    authorize_url = get_authorize_url(provider, state, redirect_uri)

    resp = RedirectResponse(url=authorize_url, status_code=302)
    resp.set_cookie(
        key=STATE_COOKIE,
        value=state,
        max_age=STATE_COOKIE_MAX_AGE,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )
    return resp


@router.get("/{provider_name}/callback")
async def oauth_callback(
    provider_name: str,
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    """Handle OAuth callback — exchange code, issue JWTs, redirect to frontend."""
    frontend = _frontend_base(request)

    if error:
        logger.warning("OAuth provider returned error", provider=provider_name, error=error)
        return RedirectResponse(
            url=f"{frontend}/login?oauth_error={error}", status_code=302
        )

    if not code or not state:
        return RedirectResponse(
            url=f"{frontend}/login?oauth_error=missing_params", status_code=302
        )

    # Validate state cookie
    cookie_state = request.cookies.get(STATE_COOKIE)
    if not cookie_state or cookie_state != state:
        logger.warning("OAuth state mismatch", provider=provider_name)
        return RedirectResponse(
            url=f"{frontend}/login?oauth_error=state_mismatch", status_code=302
        )

    oauth_config = request.app.state.settings.oauth
    providers = build_providers(oauth_config)
    provider = providers.get(provider_name)
    if provider is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"OAuth provider '{provider_name}' is not configured",
        )

    redirect_uri = _redirect_uri(request, provider_name)

    try:
        user_info = await exchange_code_and_fetch_user(provider, code, redirect_uri)
    except AuthError as e:
        logger.error("OAuth exchange failed", provider=provider_name, error=str(e))
        return RedirectResponse(
            url=f"{frontend}/login?oauth_error=exchange_failed", status_code=302
        )
    except Exception as e:
        logger.exception("OAuth callback error", provider=provider_name)
        return RedirectResponse(
            url=f"{frontend}/login?oauth_error=internal", status_code=302
        )

    auth_service = request.app.state.auth_service
    try:
        user, tokens = await auth_service.login_oauth(
            provider=provider_name,
            provider_user_id=user_info.provider_user_id,
            email=user_info.email,
            display_name=user_info.display_name,
            avatar_url=user_info.avatar_url,
        )
    except AuthError as e:
        return RedirectResponse(
            url=f"{frontend}/login?oauth_error={str(e)}", status_code=302
        )

    # Redirect to frontend with tokens in hash (not query — keeps them out of logs)
    params = urlencode({
        "access_token": tokens.access_token,
        "refresh_token": tokens.refresh_token,
        "expires_in": tokens.expires_in,
    })
    resp = RedirectResponse(url=f"{frontend}/oauth-complete#{params}", status_code=302)
    resp.delete_cookie(STATE_COOKIE, path="/")
    return resp


@router.get("/providers")
async def list_providers(request: Request) -> dict:
    """Return which OAuth providers are configured."""
    oauth_config = request.app.state.settings.oauth
    providers = build_providers(oauth_config)
    return {"providers": list(providers.keys())}
