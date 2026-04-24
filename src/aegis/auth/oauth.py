"""OAuth provider definitions — Google, GitHub, Microsoft."""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import urlencode

import httpx

from ..utils.errors import AuthError
from ..utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class OAuthUserInfo:
    """Normalized user info from an OAuth provider."""
    provider_user_id: str
    email: str
    display_name: str | None = None
    avatar_url: str | None = None


@dataclass
class OAuthProvider:
    name: str
    authorize_url: str
    token_url: str
    userinfo_url: str
    scopes: list[str]
    client_id: str
    client_secret: str
    # Callable (client: httpx.AsyncClient, access_token: str, userinfo: dict) -> OAuthUserInfo
    parse_userinfo: Callable[[dict[str, Any]], OAuthUserInfo]
    # Optional extra step to fetch email (e.g., GitHub private email)
    fetch_email: Callable[[httpx.AsyncClient, str], Any] | None = None


def _parse_google(data: dict[str, Any]) -> OAuthUserInfo:
    return OAuthUserInfo(
        provider_user_id=str(data["sub"]),
        email=data["email"],
        display_name=data.get("name"),
        avatar_url=data.get("picture"),
    )


def _parse_github(data: dict[str, Any]) -> OAuthUserInfo:
    return OAuthUserInfo(
        provider_user_id=str(data["id"]),
        email=data.get("email") or "",  # may need fetch_email
        display_name=data.get("name") or data.get("login"),
        avatar_url=data.get("avatar_url"),
    )


async def _fetch_github_email(client: httpx.AsyncClient, access_token: str) -> str:
    """GitHub users may have private primary email — fetch via /user/emails."""
    r = await client.get(
        "https://api.github.com/user/emails",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.github+json",
        },
    )
    r.raise_for_status()
    emails = r.json()
    # Prefer primary + verified
    for e in emails:
        if e.get("primary") and e.get("verified"):
            return e["email"]
    for e in emails:
        if e.get("verified"):
            return e["email"]
    if emails:
        return emails[0]["email"]
    raise AuthError("No email address available from GitHub account")


def _parse_microsoft(data: dict[str, Any]) -> OAuthUserInfo:
    return OAuthUserInfo(
        provider_user_id=str(data["id"]),
        email=data.get("mail") or data.get("userPrincipalName") or "",
        display_name=data.get("displayName"),
        avatar_url=None,  # MS Graph photo requires separate call
    )


def build_providers(config: Any) -> dict[str, OAuthProvider]:
    """Build provider registry from OAuthConfig."""
    providers: dict[str, OAuthProvider] = {}

    if config.google_client_id and config.google_client_secret:
        providers["google"] = OAuthProvider(
            name="google",
            authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
            token_url="https://oauth2.googleapis.com/token",
            userinfo_url="https://openidconnect.googleapis.com/v1/userinfo",
            scopes=["openid", "email", "profile"],
            client_id=config.google_client_id,
            client_secret=config.google_client_secret,
            parse_userinfo=_parse_google,
        )

    if config.github_client_id and config.github_client_secret:
        providers["github"] = OAuthProvider(
            name="github",
            authorize_url="https://github.com/login/oauth/authorize",
            token_url="https://github.com/login/oauth/access_token",
            userinfo_url="https://api.github.com/user",
            scopes=["read:user", "user:email"],
            client_id=config.github_client_id,
            client_secret=config.github_client_secret,
            parse_userinfo=_parse_github,
            fetch_email=_fetch_github_email,
        )

    if config.microsoft_client_id and config.microsoft_client_secret:
        tenant = config.microsoft_tenant or "common"
        providers["microsoft"] = OAuthProvider(
            name="microsoft",
            authorize_url=f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize",
            token_url=f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
            userinfo_url="https://graph.microsoft.com/v1.0/me",
            scopes=["openid", "email", "profile", "User.Read"],
            client_id=config.microsoft_client_id,
            client_secret=config.microsoft_client_secret,
            parse_userinfo=_parse_microsoft,
        )

    return providers


def generate_state() -> str:
    return secrets.token_urlsafe(32)


def get_authorize_url(provider: OAuthProvider, state: str, redirect_uri: str) -> str:
    params = {
        "client_id": provider.client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(provider.scopes),
        "state": state,
    }
    if provider.name == "google":
        params["access_type"] = "online"
        params["prompt"] = "select_account"
    elif provider.name == "microsoft":
        params["response_mode"] = "query"
    return f"{provider.authorize_url}?{urlencode(params)}"


async def exchange_code_and_fetch_user(
    provider: OAuthProvider, code: str, redirect_uri: str
) -> OAuthUserInfo:
    """Exchange auth code for access token and fetch user info. Returns normalized info."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        # Exchange code for token
        token_data = {
            "client_id": provider.client_id,
            "client_secret": provider.client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }
        headers = {"Accept": "application/json"}
        resp = await client.post(provider.token_url, data=token_data, headers=headers)
        if resp.status_code != 200:
            logger.error("OAuth token exchange failed",
                         provider=provider.name, status=resp.status_code, body=resp.text[:500])
            raise AuthError(f"OAuth token exchange failed: {resp.status_code}")
        token_resp = resp.json()
        access_token = token_resp.get("access_token")
        if not access_token:
            raise AuthError("No access_token in OAuth response")

        # Fetch userinfo
        ui_resp = await client.get(
            provider.userinfo_url,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
            },
        )
        ui_resp.raise_for_status()
        userinfo = ui_resp.json()
        user_info = provider.parse_userinfo(userinfo)

        # Fallback: fetch email separately if missing
        if not user_info.email and provider.fetch_email:
            user_info.email = await provider.fetch_email(client, access_token)

        if not user_info.email:
            raise AuthError(f"No email returned from {provider.name}")

        return user_info
