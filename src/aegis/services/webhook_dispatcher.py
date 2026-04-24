"""Outbound webhook dispatcher — sends events to registered webhook URLs."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
from typing import Any

import httpx

from ..utils.logging import get_logger

logger = get_logger(__name__)


class WebhookDispatcher:
    """Dispatches outbound webhook events asynchronously."""

    def __init__(
        self,
        repositories: Any,
        max_retries: int = 3,
        retry_delay: int = 5,
        timeout: int = 30,
    ) -> None:
        self._repos = repositories
        self._max_retries = max_retries
        self._retry_delay = retry_delay
        self._timeout = timeout

    async def dispatch(
        self,
        agent_id: str,
        event: str,
        payload: dict[str, Any],
    ) -> None:
        """Fire outbound webhooks for an agent event. Runs in background."""
        webhooks = await self._repos.webhooks.list_outbound_for_agent(agent_id, event)
        if not webhooks:
            return

        for webhook in webhooks:
            # Fire and forget — don't block the caller
            asyncio.create_task(self._deliver(webhook, event, payload))

    async def _deliver(self, webhook: Any, event: str, payload: dict[str, Any]) -> None:
        """Deliver a webhook with retries."""
        if not webhook.url:
            return

        body = json.dumps({
            "event": event,
            "agent_id": webhook.agent_id,
            "webhook_id": webhook.id,
            "data": payload,
        })

        headers: dict[str, str] = {"Content-Type": "application/json"}

        # Add HMAC signature if secret is set
        if webhook.secret:
            sig = hmac.new(
                webhook.secret.encode(), body.encode(), hashlib.sha256
            ).hexdigest()
            headers["X-Webhook-Signature"] = f"sha256={sig}"

        last_error: str | None = None
        status_code: int | None = None

        for attempt in range(self._max_retries):
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    resp = await client.post(webhook.url, content=body, headers=headers)
                    status_code = resp.status_code

                    if 200 <= resp.status_code < 300:
                        # Success
                        await self._repos.webhooks.log_delivery(
                            webhook.id, "outbound", payload,
                            response_text=resp.text[:1000], status_code=resp.status_code,
                        )
                        logger.info(
                            "Outbound webhook delivered",
                            webhook_id=webhook.id, event=event, status=resp.status_code,
                        )
                        return

                    last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"

            except Exception as e:
                last_error = str(e)

            # Wait before retry
            if attempt < self._max_retries - 1:
                await asyncio.sleep(self._retry_delay * (attempt + 1))

        # All retries failed
        await self._repos.webhooks.log_delivery(
            webhook.id, "outbound", payload,
            status_code=status_code, error=last_error,
        )
        logger.warning(
            "Outbound webhook failed",
            webhook_id=webhook.id, event=event, error=last_error,
        )
