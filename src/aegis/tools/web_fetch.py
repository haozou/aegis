"""Web fetch tool."""

from __future__ import annotations

import re
from typing import Any

import httpx

from ..utils.logging import get_logger
from .base import BaseTool
from .types import ToolContext, ToolResult

logger = get_logger(__name__)

MAX_CHARS = 20000


def _html_to_markdown(html: str) -> str:
    """Convert HTML to readable text/markdown."""
    try:
        import html2text
        h = html2text.HTML2Text()
        h.ignore_links = False
        h.ignore_images = True
        h.body_width = 0
        return h.handle(html)
    except ImportError:
        pass

    try:
        from markdownify import markdownify
        return markdownify(html)
    except ImportError:
        pass

    # Fallback: strip HTML tags
    clean = re.sub(r'<[^>]+>', ' ', html)
    clean = re.sub(r'\s+', ' ', clean)
    return clean.strip()


class WebFetchTool(BaseTool):
    """Fetch and convert web pages to markdown."""

    @property
    def name(self) -> str:
        return "web_fetch"

    @property
    def description(self) -> str:
        return (
            "Fetch the content of a URL and return it as readable text/markdown. "
            "Use for reading web pages, documentation, articles, etc."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL to fetch",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Request timeout in seconds (default: 30)",
                    "default": 30,
                },
            },
            "required": ["url"],
        }

    async def execute(self, context: ToolContext, **kwargs: Any) -> ToolResult:
        url = kwargs.get("url", "")
        timeout = min(int(kwargs.get("timeout", context.timeout)), 60)

        if not url:
            return ToolResult(output="Error: URL required", is_error=True)

        # Basic URL validation
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        logger.debug("Fetching URL", url=url)

        try:
            async with httpx.AsyncClient(
                follow_redirects=True,
                timeout=timeout,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.5",
                },
            ) as client:
                response = await client.get(url)
                response.raise_for_status()

            content_type = response.headers.get("content-type", "")
            text = response.text

            if "html" in content_type:
                text = _html_to_markdown(text)
            elif "json" in content_type:
                import json
                try:
                    parsed = json.loads(text)
                    text = json.dumps(parsed, indent=2)
                except Exception:
                    pass

            if len(text) > MAX_CHARS:
                text = text[:MAX_CHARS] + f"\n\n... [truncated at {MAX_CHARS} chars]"

            return ToolResult(
                output=text,
                metadata={"url": url, "status_code": response.status_code},
            )

        except httpx.TimeoutException:
            return ToolResult(output=f"Error: Request to {url} timed out", is_error=True)
        except httpx.HTTPStatusError as e:
            return ToolResult(output=f"HTTP Error {e.response.status_code}: {e.response.text[:500]}", is_error=True)
        except Exception as e:
            logger.error("Web fetch failed", url=url, error=str(e))
            return ToolResult(output=f"Error fetching {url}: {e}", is_error=True)
