"""Anthropic Claude provider."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import anthropic

from ...utils.errors import LLMAuthError, LLMError, LLMRateLimitError, LLMTimeoutError
from ...utils.logging import get_logger
from ..base import BaseLLMProvider
from ..types import LLMMessage, LLMRequest, LLMResponse, StreamDelta, ToolCallDelta

logger = get_logger(__name__)


def _messages_to_anthropic(messages: list[LLMMessage]) -> list[dict[str, Any]]:
    """Convert LLMMessages to Anthropic API format."""
    result = []
    for msg in messages:
        if msg.role == "system":
            continue  # System is handled separately
        if msg.role == "tool":
            # Tool result as user message with tool_result content
            result.append({
                "role": "user",
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": msg.tool_call_id or "",
                    "content": msg.content if isinstance(msg.content, str) else json.dumps(msg.content),
                }],
            })
        elif msg.role == "assistant" and msg.tool_calls:
            # Assistant with tool calls
            content: list[dict[str, Any]] = []
            if isinstance(msg.content, str) and msg.content:
                content.append({"type": "text", "text": msg.content})
            for tc in msg.tool_calls:
                content.append({
                    "type": "tool_use",
                    "id": tc.get("id", ""),
                    "name": tc.get("name", ""),
                    "input": tc.get("input", {}),
                })
            result.append({"role": "assistant", "content": content})
        else:
            result.append({
                "role": msg.role,
                "content": msg.content,
            })
    return result


def _tools_to_anthropic(tools: list[Any]) -> list[dict[str, Any]]:
    """Convert ToolDefinitions to Anthropic format."""
    return [
        {
            "name": t.name,
            "description": t.description,
            "input_schema": t.parameters,
        }
        for t in tools
    ]


class AnthropicProvider(BaseLLMProvider):
    """Anthropic Claude provider."""

    name = "anthropic"

    def __init__(self, api_key: str = "", base_url: str = "") -> None:
        kwargs: dict[str, Any] = {}
        if api_key:
            kwargs["api_key"] = api_key
        if base_url:
            kwargs["base_url"] = base_url
        # If using a local proxy that doesn't require auth,
        # set a dummy key so the SDK doesn't complain
        if base_url and not api_key:
            kwargs["api_key"] = "not-needed"
        self._client = anthropic.AsyncAnthropic(**kwargs)

    def get_default_model(self) -> str:
        return "claude-sonnet-4-5"

    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Non-streaming completion."""
        system = request.system_prompt or ""
        messages = _messages_to_anthropic(request.messages)
        kwargs: dict[str, Any] = dict(
            model=request.model,
            max_tokens=request.max_tokens,
            messages=messages,
            temperature=request.temperature,
        )
        if system:
            kwargs["system"] = system
        if request.tools:
            kwargs["tools"] = _tools_to_anthropic(request.tools)

        try:
            response = await self._client.messages.create(**kwargs)
        except anthropic.AuthenticationError as e:
            raise LLMAuthError(str(e)) from e
        except anthropic.RateLimitError as e:
            raise LLMRateLimitError(str(e)) from e
        except anthropic.APITimeoutError as e:
            raise LLMTimeoutError(str(e)) from e
        except anthropic.APIError as e:
            raise LLMError(str(e)) from e

        text_content = ""
        tool_calls = []
        for block in response.content:
            if block.type == "text":
                text_content += block.text
            elif block.type == "tool_use":
                tool_calls.append({
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                })

        return LLMResponse(
            content=text_content,
            tool_calls=tool_calls,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            model=response.model,
            stop_reason=response.stop_reason or "end_turn",
        )

    async def stream(self, request: LLMRequest) -> AsyncIterator[StreamDelta]:
        """Streaming completion."""
        system = request.system_prompt or ""
        messages = _messages_to_anthropic(request.messages)
        kwargs: dict[str, Any] = dict(
            model=request.model,
            max_tokens=request.max_tokens,
            messages=messages,
            temperature=request.temperature,
        )
        if system:
            kwargs["system"] = system
        if request.tools:
            kwargs["tools"] = _tools_to_anthropic(request.tools)

        try:
            async with self._client.messages.stream(**kwargs) as stream:
                current_tool: dict[str, Any] | None = None
                input_tokens = 0
                output_tokens = 0

                async for event in stream:
                    event_type = type(event).__name__

                    if event_type.endswith("MessageStartEvent"):
                        msg = getattr(event, "message", None)
                        usage = getattr(msg, "usage", None) if msg else None
                        if usage:
                            input_tokens = getattr(usage, "input_tokens", 0)

                    elif event_type.endswith("ContentBlockStartEvent"):
                        block = getattr(event, "content_block", None)
                        if block and getattr(block, "type", None) == "tool_use":
                            current_tool = {"id": block.id, "name": block.name, "input_json": ""}
                            yield StreamDelta(
                                is_tool_start=True,
                                tool_call_id=block.id,
                                tool_name=block.name,
                            )

                    elif event_type.endswith("ContentBlockDeltaEvent"):
                        delta = event.delta
                        if getattr(delta, "type", None) == "text_delta":
                            yield StreamDelta(text=delta.text)
                        elif getattr(delta, "type", None) == "input_json_delta" and current_tool is not None:
                            current_tool["input_json"] = current_tool.get("input_json", "") + delta.partial_json

                    elif event_type.endswith("ContentBlockStopEvent"):
                        if current_tool is not None:
                            try:
                                tool_input = json.loads(current_tool["input_json"] or "{}")
                            except json.JSONDecodeError:
                                tool_input = {}
                            yield StreamDelta(
                                tool_call_id=current_tool["id"],
                                tool_name=current_tool["name"],
                                tool_input=tool_input,
                            )
                            current_tool = None

                    elif event_type.endswith("MessageDeltaEvent"):
                        usage = getattr(event, "usage", None)
                        if usage:
                            output_tokens = getattr(usage, "output_tokens", 0) or 0

                yield StreamDelta(
                    is_done=True,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                )

        except anthropic.AuthenticationError as e:
            raise LLMAuthError(str(e)) from e
        except anthropic.RateLimitError as e:
            raise LLMRateLimitError(str(e)) from e
        except anthropic.APITimeoutError as e:
            raise LLMTimeoutError(str(e)) from e
        except anthropic.APIError as e:
            raise LLMError(str(e)) from e

    async def health_check(self) -> bool:
        try:
            await self._client.models.list()
            return True
        except Exception:
            return False
