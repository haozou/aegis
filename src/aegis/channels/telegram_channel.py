"""Telegram channel adapter.

Uses Telegram's webhook API — Telegram pushes updates to your server.
Registers the webhook URL at startup via setWebhook.

Requires: pip install httpx
"""

from __future__ import annotations

from typing import Any

import httpx

from ..utils.logging import get_logger
from .base import BaseChannel, InboundMessage

logger = get_logger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"


class TelegramChannel(BaseChannel):
    """Handles Telegram bot messages via webhook."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._bot_token: str = ""

    async def start(self) -> None:
        self._bot_token = self.config.get("bot_token", "")
        if not self._bot_token:
            logger.error("Telegram bot_token missing", connection_id=self.connection_id)
            return

        webhook_url: str = self.config.get("webhook_url", "")
        if webhook_url:
            await self._register_webhook(webhook_url)

        self._running = True
        logger.info("Telegram adapter started", connection_id=self.connection_id)

    async def stop(self) -> None:
        self._running = False
        logger.info("Telegram adapter stopped", connection_id=self.connection_id)

    async def send_reply(self, msg: InboundMessage, reply_text: str) -> None:
        chat_id = msg.external_chat_id
        # Telegram message limit is 4096 chars
        for chunk in _split_message(reply_text, 4096):
            await self._api_call(
                "sendMessage",
                {"chat_id": chat_id, "text": chunk, "parse_mode": "Markdown"},
            )

    async def handle_update(self, update: dict[str, Any]) -> None:
        """Called by the FastAPI webhook route when Telegram pushes an update."""
        if not self._running:
            return

        message = update.get("message") or update.get("edited_message")
        if not message:
            return

        text: str = message.get("text", "").strip()
        if not text:
            return

        chat = message.get("chat", {})
        sender = message.get("from", {})

        inbound = InboundMessage(
            channel_type="telegram",
            external_user_id=str(sender.get("id", "")),
            external_chat_id=str(chat.get("id", "")),
            text=text,
            raw={
                "update_id": update.get("update_id"),
                "message_id": message.get("message_id"),
                "chat_type": chat.get("type"),
                "username": sender.get("username"),
            },
        )
        await self.handle_message(inbound)

    async def _register_webhook(self, webhook_url: str) -> None:
        secret = self.config.get("webhook_secret", "")
        payload: dict[str, Any] = {"url": webhook_url}
        if secret:
            payload["secret_token"] = secret
        try:
            result = await self._api_call("setWebhook", payload)
            if result.get("ok"):
                logger.info(
                    "Telegram webhook registered",
                    connection_id=self.connection_id,
                    url=webhook_url,
                )
            else:
                logger.warning(
                    "Telegram setWebhook failed",
                    connection_id=self.connection_id,
                    result=result,
                )
        except Exception as exc:
            logger.error(
                "Telegram webhook registration error",
                connection_id=self.connection_id,
                error=str(exc),
            )

    async def _api_call(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = TELEGRAM_API.format(token=self._bot_token, method=method)
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            return resp.json()


def _split_message(text: str, limit: int) -> list[str]:
    if len(text) <= limit:
        return [text]
    parts: list[str] = []
    while text:
        parts.append(text[:limit])
        text = text[limit:]
    return parts
