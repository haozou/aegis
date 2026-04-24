"""SMS channel adapter via Twilio.

Twilio calls your webhook URL when an SMS arrives.
Replies are sent via Twilio's REST API.

Requires: pip install httpx
"""

from __future__ import annotations

from typing import Any

import httpx

from ..utils.logging import get_logger
from .base import BaseChannel, InboundMessage

logger = get_logger(__name__)

TWILIO_API = "https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"


class SMSChannel(BaseChannel):
    """Handles inbound SMS via Twilio webhook and replies via Twilio REST API."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

    async def start(self) -> None:
        required = ("account_sid", "auth_token", "from_number")
        for key in required:
            if not self.config.get(key):
                logger.error(
                    f"SMS channel missing config key: {key}",
                    connection_id=self.connection_id,
                )
                return

        self._running = True
        logger.info("SMS adapter started", connection_id=self.connection_id)

    async def stop(self) -> None:
        self._running = False
        logger.info("SMS adapter stopped", connection_id=self.connection_id)

    async def send_reply(self, msg: InboundMessage, reply_text: str) -> None:
        account_sid: str = self.config["account_sid"]
        auth_token: str = self.config["auth_token"]
        from_number: str = self.config["from_number"]
        to_number: str = msg.external_user_id

        # SMS practical limit ~1600 chars (Twilio will split if needed, but let's be safe)
        for chunk in _split_message(reply_text, 1600):
            try:
                url = TWILIO_API.format(sid=account_sid)
                async with httpx.AsyncClient(timeout=15) as client:
                    resp = await client.post(
                        url,
                        data={"From": from_number, "To": to_number, "Body": chunk},
                        auth=(account_sid, auth_token),
                    )
                    resp.raise_for_status()
            except Exception as exc:
                logger.error(
                    "Twilio SMS send error",
                    connection_id=self.connection_id,
                    to=to_number,
                    error=str(exc),
                )

    async def handle_inbound(self, form_data: dict[str, str]) -> str:
        """Called by the FastAPI webhook route with Twilio's form-encoded data.

        Returns a TwiML response string (empty <Response> since we reply async).
        """
        if not self._running:
            return "<Response/>"

        from_number: str = form_data.get("From", "")
        body: str = form_data.get("Body", "").strip()

        if not from_number or not body:
            return "<Response/>"

        inbound = InboundMessage(
            channel_type="sms",
            external_user_id=from_number,
            external_chat_id=from_number,  # one convo per phone number
            text=body,
            raw={
                "to": form_data.get("To", ""),
                "from": from_number,
                "sms_sid": form_data.get("SmsSid", ""),
                "num_media": form_data.get("NumMedia", "0"),
            },
        )
        # Fire and forget — Twilio requires a quick HTTP response
        import asyncio
        asyncio.create_task(self.handle_message(inbound))
        return "<Response/>"


def _split_message(text: str, limit: int) -> list[str]:
    if len(text) <= limit:
        return [text]
    parts: list[str] = []
    while text:
        parts.append(text[:limit])
        text = text[limit:]
    return parts
