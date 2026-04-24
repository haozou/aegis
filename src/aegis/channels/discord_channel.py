"""Discord channel adapter.

Requires: pip install discord.py
"""

from __future__ import annotations

import asyncio
from typing import Any

from ..utils.logging import get_logger
from .base import BaseChannel, InboundMessage

logger = get_logger(__name__)


class DiscordChannel(BaseChannel):
    """Listens on the Discord gateway and routes messages to the agent."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._client: Any = None
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        try:
            import discord
        except ImportError:
            logger.error("discord.py not installed — run: pip install discord.py")
            return

        bot_token: str = self.config.get("bot_token", "")
        if not bot_token:
            logger.error("Discord bot_token missing", connection_id=self.connection_id)
            return

        allowed_channel_ids: set[int] = {
            int(c) for c in self.config.get("channel_ids", []) if c
        }

        intents = discord.Intents.default()
        intents.message_content = True
        client = discord.Client(intents=intents)
        self._client = client

        channel_adapter = self  # capture for closure

        @client.event
        async def on_ready() -> None:
            logger.info(
                "Discord bot connected",
                connection_id=channel_adapter.connection_id,
                bot=str(client.user),
            )

        @client.event
        async def on_message(message: Any) -> None:
            # Ignore own messages
            if message.author == client.user:
                return
            # Filter to configured channels if any are set
            if allowed_channel_ids and message.channel.id not in allowed_channel_ids:
                return

            msg = InboundMessage(
                channel_type="discord",
                external_user_id=str(message.author.id),
                external_chat_id=str(message.channel.id),
                text=message.content,
                raw={
                    "guild_id": str(message.guild.id) if message.guild else None,
                    "channel_id": str(message.channel.id),
                    "message_id": str(message.id),
                    "author_name": str(message.author),
                },
            )

            async with message.channel.typing():
                await channel_adapter.handle_message(msg)

        self._running = True
        # Run the bot in a background task so startup returns immediately
        self._task = asyncio.create_task(
            client.start(bot_token), name=f"discord-{self.connection_id}"
        )
        logger.info("Discord adapter started", connection_id=self.connection_id)

    async def stop(self) -> None:
        self._running = False
        if self._client is not None:
            try:
                await self._client.close()
            except Exception as exc:
                logger.warning("Discord client close error", error=str(exc))
            self._client = None
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None
        logger.info("Discord adapter stopped", connection_id=self.connection_id)

    async def send_reply(self, msg: InboundMessage, reply_text: str) -> None:
        if self._client is None:
            return
        channel_id = int(msg.external_chat_id)
        channel = self._client.get_channel(channel_id)
        if channel is None:
            logger.warning(
                "Discord channel not found for reply",
                channel_id=channel_id,
                connection_id=self.connection_id,
            )
            return
        # Split long messages (Discord 2000 char limit)
        for chunk in _split_message(reply_text, 2000):
            await channel.send(chunk)


def _split_message(text: str, limit: int) -> list[str]:
    if len(text) <= limit:
        return [text]
    parts: list[str] = []
    while text:
        parts.append(text[:limit])
        text = text[limit:]
    return parts
