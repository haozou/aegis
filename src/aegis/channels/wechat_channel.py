"""WeChat Official Account channel adapter.

Uses WeChat's push webhook model:
  - WeChat sends an XML POST to your server when a message arrives
  - You must reply within 5 seconds (we return "success" immediately and
    send the actual reply via the Customer Service API asynchronously)
  - Access tokens expire every 7200 seconds and are refreshed automatically

Supports: WeChat Official Account (公众号) — text messages only.
Enterprise WeChat (企业微信) uses a different API; see wechat_work_channel.py.

Requires: pip install httpx

Config fields:
    app_id         WeChat AppID (from mp.weixin.qq.com → Basic Config)
    app_secret     WeChat AppSecret
    token          Verification token (you choose this; must match WeChat dashboard)
    encoding_aes_key  (optional) Message encryption key for encrypted mode
"""

from __future__ import annotations

import asyncio
import hashlib
import time
import xml.etree.ElementTree as ET
from typing import Any

import httpx

from ..utils.logging import get_logger
from .base import BaseChannel, InboundMessage

logger = get_logger(__name__)

WECHAT_API = "https://api.weixin.qq.com/cgi-bin"


class WeChatChannel(BaseChannel):
    """Handles WeChat Official Account messages via push webhook.

    Flow:
        1. WeChat GETs the webhook URL to verify the server (echostr handshake)
        2. WeChat POSTs XML when a user sends a message
        3. We return "success" immediately (fire-and-forget)
        4. Agent runs and reply is sent via Customer Service API (sendMessage)
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._access_token: str = ""
        self._token_expires_at: float = 0.0
        self._refresh_task: asyncio.Task[None] | None = None

    # ------------------------------------------------------------------ #
    # Lifecycle                                                           #
    # ------------------------------------------------------------------ #

    async def start(self) -> None:
        required = ("app_id", "app_secret", "token")
        for key in required:
            if not self.config.get(key):
                logger.error(
                    f"WeChat channel missing config key: {key}",
                    connection_id=self.connection_id,
                )
                return

        # Fetch the initial access token
        await self._refresh_access_token()

        # Schedule background token refresh
        self._refresh_task = asyncio.create_task(self._token_refresh_loop())

        self._running = True
        logger.info(
            "WeChat adapter started",
            connection_id=self.connection_id,
            app_id=self.config.get("app_id", "")[:8] + "...",
        )

    async def stop(self) -> None:
        self._running = False
        if self._refresh_task and not self._refresh_task.done():
            self._refresh_task.cancel()
            try:
                await self._refresh_task
            except asyncio.CancelledError:
                pass
        self._refresh_task = None
        logger.info("WeChat adapter stopped", connection_id=self.connection_id)

    # ------------------------------------------------------------------ #
    # Inbound — called by FastAPI route                                   #
    # ------------------------------------------------------------------ #

    def verify_signature(self, timestamp: str, nonce: str, signature: str) -> bool:
        """Verify WeChat's SHA1 signature for webhook validation."""
        token: str = self.config.get("token", "")
        parts = sorted([token, timestamp, nonce])
        computed = hashlib.sha1("".join(parts).encode()).hexdigest()
        return computed == signature

    async def handle_verify(
        self, timestamp: str, nonce: str, signature: str, echostr: str
    ) -> str | None:
        """Handle WeChat's GET verification handshake.

        Returns echostr on success, None on failure.
        """
        if self.verify_signature(timestamp, nonce, signature):
            return echostr
        logger.warning(
            "WeChat signature verification failed",
            connection_id=self.connection_id,
        )
        return None

    async def handle_update(self, body: bytes, timestamp: str, nonce: str, signature: str) -> str:
        """Called by the FastAPI webhook route when WeChat pushes a message.

        Verifies the signature, parses the XML, fires agent execution in the
        background, and returns "success" immediately so WeChat doesn't retry.
        """
        if not self._running:
            return "success"

        # Verify signature
        if not self.verify_signature(timestamp, nonce, signature):
            logger.warning(
                "WeChat message signature invalid",
                connection_id=self.connection_id,
            )
            return "success"

        # Parse XML
        try:
            root = ET.fromstring(body)
        except ET.ParseError as exc:
            logger.error(
                "WeChat XML parse error",
                connection_id=self.connection_id,
                error=str(exc),
            )
            return "success"

        msg_type = _xml_text(root, "MsgType")
        if msg_type != "text":
            # Non-text messages (images, voice, etc.) are acknowledged but not processed
            return "success"

        open_id = _xml_text(root, "FromUserName")
        text = _xml_text(root, "Content").strip()

        if not open_id or not text:
            return "success"

        inbound = InboundMessage(
            channel_type="wechat",
            external_user_id=open_id,
            external_chat_id=open_id,  # WeChat is 1-to-1; one conversation per openid
            text=text,
            raw={
                "msg_id": _xml_text(root, "MsgId"),
                "to_user": _xml_text(root, "ToUserName"),
                "create_time": _xml_text(root, "CreateTime"),
            },
        )

        # Fire and forget — WeChat requires a response within 5 seconds
        asyncio.create_task(self.handle_message(inbound))
        return "success"

    # ------------------------------------------------------------------ #
    # Outbound                                                            #
    # ------------------------------------------------------------------ #

    async def send_reply(self, msg: InboundMessage, reply_text: str) -> None:
        """Send the agent reply via WeChat Customer Service (客服) API."""
        open_id = msg.external_user_id
        token = await self._get_access_token()
        if not token:
            logger.error(
                "WeChat send_reply: no access token available",
                connection_id=self.connection_id,
            )
            return

        # WeChat text message limit is 2048 characters (unofficial; official docs
        # don't state a hard limit, but the customer service API works best under 2048)
        for chunk in _split_message(reply_text, 2048):
            await self._send_customer_service_message(open_id, chunk, token)

    # ------------------------------------------------------------------ #
    # Access token management                                             #
    # ------------------------------------------------------------------ #

    async def _get_access_token(self) -> str:
        """Return a valid access token, refreshing if needed."""
        if time.monotonic() >= self._token_expires_at - 60:
            await self._refresh_access_token()
        return self._access_token

    async def _refresh_access_token(self) -> None:
        app_id: str = self.config.get("app_id", "")
        app_secret: str = self.config.get("app_secret", "")
        if not app_id or not app_secret:
            return

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{WECHAT_API}/token",
                    params={
                        "grant_type": "client_credential",
                        "appid": app_id,
                        "secret": app_secret,
                    },
                )
                resp.raise_for_status()
                data = resp.json()

            if "access_token" in data:
                self._access_token = data["access_token"]
                expires_in: int = data.get("expires_in", 7200)
                self._token_expires_at = time.monotonic() + expires_in
                logger.info(
                    "WeChat access token refreshed",
                    connection_id=self.connection_id,
                    expires_in=expires_in,
                )
            else:
                logger.error(
                    "WeChat token refresh failed",
                    connection_id=self.connection_id,
                    errcode=data.get("errcode"),
                    errmsg=data.get("errmsg"),
                )
        except Exception as exc:
            logger.error(
                "WeChat token refresh error",
                connection_id=self.connection_id,
                error=str(exc),
            )

    async def _token_refresh_loop(self) -> None:
        """Background task: refresh the access token before it expires."""
        while True:
            try:
                # Sleep until 60 seconds before expiry (or 60s if no token yet)
                remaining = self._token_expires_at - time.monotonic()
                sleep_for = max(remaining - 60, 60)
                await asyncio.sleep(sleep_for)
                await self._refresh_access_token()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning(
                    "WeChat token refresh loop error",
                    connection_id=self.connection_id,
                    error=str(exc),
                )
                await asyncio.sleep(60)

    # ------------------------------------------------------------------ #
    # WeChat API calls                                                    #
    # ------------------------------------------------------------------ #

    async def _send_customer_service_message(
        self, open_id: str, text: str, token: str
    ) -> None:
        """POST a text message to the WeChat Customer Service API."""
        url = f"{WECHAT_API}/message/custom/send"
        payload = {
            "touser": open_id,
            "msgtype": "text",
            "text": {"content": text},
        }
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    url,
                    params={"access_token": token},
                    json=payload,
                )
                resp.raise_for_status()
                result = resp.json()
                if result.get("errcode", 0) != 0:
                    logger.error(
                        "WeChat sendMessage API error",
                        connection_id=self.connection_id,
                        open_id=open_id,
                        errcode=result.get("errcode"),
                        errmsg=result.get("errmsg"),
                    )
        except Exception as exc:
            logger.error(
                "WeChat send_reply error",
                connection_id=self.connection_id,
                open_id=open_id,
                error=str(exc),
            )


# ── Helpers ───────────────────────────────────────────────────────────────────


def _xml_text(root: ET.Element, tag: str) -> str:
    el = root.find(tag)
    return (el.text or "").strip() if el is not None else ""


def _split_message(text: str, limit: int) -> list[str]:
    if len(text) <= limit:
        return [text]
    parts: list[str] = []
    while text:
        parts.append(text[:limit])
        text = text[limit:]
    return parts
