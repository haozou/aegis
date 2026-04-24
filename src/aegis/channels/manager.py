"""Channel manager — lifecycle management for all channel adapters."""

from __future__ import annotations

from typing import Any

from ..utils.logging import get_logger
from .base import BaseChannel
from .discord_channel import DiscordChannel
from .email_channel import EmailChannel
from .sms_channel import SMSChannel
from .telegram_channel import TelegramChannel
from .wechat_channel import WeChatChannel

logger = get_logger(__name__)

_ADAPTER_MAP: dict[str, type[BaseChannel]] = {
    "discord": DiscordChannel,
    "email": EmailChannel,
    "telegram": TelegramChannel,
    "sms": SMSChannel,
    "wechat": WeChatChannel,
}


class ChannelManager:
    """Manages the lifecycle of all channel adapters.

    On startup it loads every active `channel_connection` from the database
    and spins up the appropriate adapter. Routes provide `reload_connection`
    and `remove_connection` to handle create/update/delete events.
    """

    def __init__(self, repos: Any, orchestrator: Any, db: Any) -> None:
        self._repos = repos
        self._orchestrator = orchestrator
        self._db = db
        self._adapters: dict[str, BaseChannel] = {}  # connection_id → adapter

    # ------------------------------------------------------------------ #
    # Lifecycle                                                           #
    # ------------------------------------------------------------------ #

    async def start(self) -> None:
        """Load all active connections and start their adapters."""
        connections = await self._repos.channels.list_active()
        for conn in connections:
            await self._start_adapter(conn)
        logger.info("ChannelManager started", adapters=len(self._adapters))

    async def stop(self) -> None:
        """Stop all running adapters."""
        for conn_id, adapter in list(self._adapters.items()):
            await self._stop_adapter(conn_id, adapter)
        self._adapters.clear()
        logger.info("ChannelManager stopped")

    # ------------------------------------------------------------------ #
    # Public API — called from HTTP route handlers                        #
    # ------------------------------------------------------------------ #

    async def reload_connection(self, connection_id: str) -> None:
        """Stop the old adapter (if any) and start a fresh one."""
        await self.remove_connection(connection_id)

        conn = await self._repos.channels.get(connection_id)
        if conn and conn.is_active:
            await self._start_adapter(conn)

    async def remove_connection(self, connection_id: str) -> None:
        """Stop and discard the adapter for a connection."""
        adapter = self._adapters.pop(connection_id, None)
        if adapter is not None:
            await self._stop_adapter(connection_id, adapter)

    def get_adapter(self, connection_id: str) -> BaseChannel | None:
        return self._adapters.get(connection_id)

    # ------------------------------------------------------------------ #
    # Internal helpers                                                    #
    # ------------------------------------------------------------------ #

    async def _start_adapter(self, conn: Any) -> None:
        adapter_cls = _ADAPTER_MAP.get(conn.channel_type)
        if adapter_cls is None:
            logger.warning(
                "Unknown channel type",
                channel_type=conn.channel_type,
                connection_id=conn.id,
            )
            return

        adapter = adapter_cls(
            connection_id=conn.id,
            agent_id=conn.agent_id,
            user_id=conn.user_id,
            config=conn.config,
            orchestrator=self._orchestrator,
            db=self._db,
            repos=self._repos,
        )
        try:
            await adapter.start()
            self._adapters[conn.id] = adapter
            logger.info(
                "Channel adapter started",
                connection_id=conn.id,
                channel_type=conn.channel_type,
                agent_id=conn.agent_id,
            )
        except Exception as exc:
            logger.error(
                "Channel adapter start failed",
                connection_id=conn.id,
                channel_type=conn.channel_type,
                error=str(exc),
            )

    async def _stop_adapter(self, connection_id: str, adapter: BaseChannel) -> None:
        try:
            await adapter.stop()
            logger.info("Channel adapter stopped", connection_id=connection_id)
        except Exception as exc:
            logger.warning(
                "Channel adapter stop error",
                connection_id=connection_id,
                error=str(exc),
            )
