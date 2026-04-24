"""Email channel adapter.

Polls an IMAP mailbox for new messages and replies via SMTP.

Requires: pip install aiosmtplib aioimaplib
"""

from __future__ import annotations

import asyncio
import email as email_lib
import email.header
import email.utils
from email.mime.text import MIMEText
from typing import Any

from ..utils.logging import get_logger
from .base import BaseChannel, InboundMessage

logger = get_logger(__name__)

DEFAULT_POLL_INTERVAL = 60  # seconds


class EmailChannel(BaseChannel):
    """Polls IMAP for new mail and replies via SMTP."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._task: asyncio.Task[None] | None = None
        self._seen_ids: set[str] = set()

    async def start(self) -> None:
        required = ("imap_host", "imap_user", "imap_pass", "smtp_host", "address")
        for key in required:
            if not self.config.get(key):
                logger.error(
                    f"Email channel missing config key: {key}",
                    connection_id=self.connection_id,
                )
                return

        self._running = True
        self._task = asyncio.create_task(
            self._poll_loop(), name=f"email-{self.connection_id}"
        )
        logger.info("Email adapter started", connection_id=self.connection_id)

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None
        logger.info("Email adapter stopped", connection_id=self.connection_id)

    async def send_reply(self, msg: InboundMessage, reply_text: str) -> None:
        try:
            import aiosmtplib
        except ImportError:
            logger.error("aiosmtplib not installed — run: pip install aiosmtplib")
            return

        smtp_host: str = self.config["smtp_host"]
        smtp_port: int = int(self.config.get("smtp_port", 587))
        smtp_user: str = self.config.get("smtp_user") or self.config["imap_user"]
        smtp_pass: str = self.config.get("smtp_pass") or self.config["imap_pass"]
        from_address: str = self.config["address"]

        mime = MIMEText(reply_text, "plain", "utf-8")
        mime["From"] = from_address
        mime["To"] = msg.external_user_id
        mime["Subject"] = f"Re: {msg.raw.get('subject', '')}"
        if msg.raw.get("message_id"):
            mime["In-Reply-To"] = msg.raw["message_id"]
            mime["References"] = msg.raw["message_id"]

        try:
            await aiosmtplib.send(
                mime,
                hostname=smtp_host,
                port=smtp_port,
                username=smtp_user,
                password=smtp_pass,
                start_tls=True,
            )
        except Exception as exc:
            logger.error("SMTP send error", connection_id=self.connection_id, error=str(exc))

    # ------------------------------------------------------------------ #

    async def _poll_loop(self) -> None:
        interval = int(self.config.get("poll_interval", DEFAULT_POLL_INTERVAL))
        while self._running:
            try:
                await self._fetch_and_handle()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(
                    "Email poll error", connection_id=self.connection_id, error=str(exc)
                )
            await asyncio.sleep(interval)

    async def _fetch_and_handle(self) -> None:
        try:
            import aioimaplib
        except ImportError:
            logger.error("aioimaplib not installed — run: pip install aioimaplib")
            self._running = False
            return

        imap_host: str = self.config["imap_host"]
        imap_port: int = int(self.config.get("imap_port", 993))
        imap_user: str = self.config["imap_user"]
        imap_pass: str = self.config["imap_pass"]

        client = aioimaplib.IMAP4_SSL(host=imap_host, port=imap_port)
        await client.wait_hello_from_server()
        await client.login(imap_user, imap_pass)
        await client.select("INBOX")

        _, data = await client.search("UNSEEN")
        message_ids: list[bytes] = data[0].split() if data and data[0] else []

        for msg_num in message_ids:
            try:
                _, msg_data = await client.fetch(msg_num.decode(), "(RFC822)")
                raw_bytes: bytes = msg_data[1]
                parsed = email_lib.message_from_bytes(raw_bytes)

                msg_id = parsed.get("Message-ID", "").strip()
                if msg_id in self._seen_ids:
                    continue
                if msg_id:
                    self._seen_ids.add(msg_id)

                from_addr = email.utils.parseaddr(parsed.get("From", ""))[1]
                subject = _decode_header(parsed.get("Subject", ""))
                body = _extract_text_body(parsed)

                if not body.strip():
                    continue

                # Use Message-ID as the thread ID so replies continue in the same convo
                thread_id = msg_id or f"{from_addr}:{subject}"

                inbound = InboundMessage(
                    channel_type="email",
                    external_user_id=from_addr,
                    external_chat_id=thread_id,
                    text=body.strip(),
                    raw={
                        "subject": subject,
                        "from": from_addr,
                        "message_id": msg_id,
                    },
                )
                await self.handle_message(inbound)
            except Exception as exc:
                logger.warning(
                    "Email message processing error",
                    connection_id=self.connection_id,
                    error=str(exc),
                )

        await client.logout()


def _decode_header(value: str) -> str:
    parts = email.header.decode_header(value)
    decoded: list[str] = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(part)
    return "".join(decoded)


def _extract_text_body(msg: Any) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    return payload.decode(part.get_content_charset() or "utf-8", errors="replace")
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            return payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
    return ""
