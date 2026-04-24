"""Web search tool — uses DuckDuckGo for search results."""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import quote_plus

import httpx

from ..utils.logging import get_logger
from .base import BaseTool
from .types import ToolContext, ToolResult

logger = get_logger(__name__)


class WebSearchTool(BaseTool):
    """Search the web using DuckDuckGo and return results."""

    @property
    def name(self) -> str:
        return "web_search"

    @property
    def description(self) -> str:
        return (
            "Search the web and return relevant results. "
            "Use this to find current information, news, prices, weather, etc. "
            "Returns titles, URLs, and snippets from search results."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results (default: 5)",
                    "default": 5,
                },
            },
            "required": ["query"],
        }

    async def execute(self, context: ToolContext, **kwargs: Any) -> ToolResult:
        query = kwargs.get("query", "").strip()
        max_results = min(int(kwargs.get("max_results", 5)), 10)

        if not query:
            return ToolResult(output="Error: search query required", is_error=True)

        logger.info("Web search", query=query)

        try:
            # Use DuckDuckGo HTML search (no API key needed)
            url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
            async with httpx.AsyncClient(
                timeout=15,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                },
                follow_redirects=True,
            ) as client:
                response = await client.get(url)
                response.raise_for_status()

            html = response.text

            # Parse results from DuckDuckGo HTML
            results = []
            # Find result blocks
            result_pattern = re.compile(
                r'<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>.*?'
                r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>',
                re.DOTALL,
            )

            for match in result_pattern.finditer(html):
                if len(results) >= max_results:
                    break
                href = match.group(1)
                title = re.sub(r'<[^>]+>', '', match.group(2)).strip()
                snippet = re.sub(r'<[^>]+>', '', match.group(3)).strip()

                # DuckDuckGo wraps URLs in redirect links
                if 'uddg=' in href:
                    from urllib.parse import unquote, parse_qs, urlparse
                    parsed = urlparse(href)
                    params = parse_qs(parsed.query)
                    if 'uddg' in params:
                        href = unquote(params['uddg'][0])

                if title and snippet:
                    results.append({
                        "title": title,
                        "url": href,
                        "snippet": snippet,
                    })

            if not results:
                # Fallback: try a simpler pattern
                simple_pattern = re.compile(
                    r'<a[^>]*class="result__url"[^>]*href="([^"]*)"[^>]*>.*?</a>.*?'
                    r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>',
                    re.DOTALL,
                )
                for match in simple_pattern.finditer(html):
                    if len(results) >= max_results:
                        break
                    href = match.group(1).strip()
                    snippet = re.sub(r'<[^>]+>', '', match.group(2)).strip()
                    if snippet:
                        results.append({"title": "", "url": href, "snippet": snippet})

            if not results:
                return ToolResult(output=f"No results found for: {query}")

            # Format results
            output_lines = [f"Search results for: {query}\n"]
            for i, r in enumerate(results, 1):
                output_lines.append(f"{i}. {r['title']}")
                output_lines.append(f"   URL: {r['url']}")
                output_lines.append(f"   {r['snippet']}")
                output_lines.append("")

            return ToolResult(
                output="\n".join(output_lines),
                metadata={"query": query, "result_count": len(results)},
            )

        except Exception as e:
            logger.error("Web search failed", query=query, error=str(e))
            return ToolResult(output=f"Search error: {e}", is_error=True)
