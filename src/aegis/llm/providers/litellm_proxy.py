"""LiteLLM proxy provider — routes all models through a single OpenAI-compatible endpoint."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
import openai as openai_lib
from openai import AsyncOpenAI

from ...utils.errors import LLMAuthError, LLMError, LLMRateLimitError, LLMTimeoutError
from ...utils.logging import get_logger
from ..base import BaseLLMProvider
from ..types import LLMMessage, LLMRequest, LLMResponse, StreamDelta, ToolCallDelta

logger = get_logger(__name__)


def _messages_to_openai(messages: list[LLMMessage]) -> list[dict[str, Any]]:
    result = []
    for msg in messages:
        if msg.role == "tool":
            result.append({
                "role": "tool",
                "tool_call_id": msg.tool_call_id or "",
                "content": msg.content if isinstance(msg.content, str) else json.dumps(msg.content),
            })
        elif msg.role == "assistant" and msg.tool_calls:
            result.append({
                "role": "assistant",
                "content": msg.content if isinstance(msg.content, str) else None,
                "tool_calls": [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": json.dumps(tc.get("input", {})),
                        },
                    }
                    for tc in msg.tool_calls
                ],
            })
        else:
            # Convert multimodal content (Anthropic format → OpenAI format)
            content = msg.content
            if isinstance(content, list):
                openai_parts = []
                for part in content:
                    if isinstance(part, dict):
                        ptype = part.get("type", "")
                        if ptype == "text":
                            openai_parts.append({"type": "text", "text": part.get("text", "")})
                        elif ptype == "image" and isinstance(part.get("source"), dict):
                            src = part["source"]
                            media_type = src.get("media_type", "image/png")
                            b64_data = src.get("data", "")
                            openai_parts.append({
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{media_type};base64,{b64_data}",
                                },
                            })
                        elif ptype == "image_url":
                            # Already in OpenAI format
                            openai_parts.append(part)
                        elif ptype == "document" and isinstance(part.get("source"), dict):
                            # PDF — some providers support this, pass as-is or fall back to text
                            openai_parts.append({"type": "text", "text": f"[Attached PDF document]"})
                        else:
                            # Unknown part — pass through as text
                            openai_parts.append({"type": "text", "text": json.dumps(part)})
                    elif isinstance(part, str):
                        openai_parts.append({"type": "text", "text": part})
                content = openai_parts
            result.append({"role": msg.role, "content": content})
    return result


def _tools_to_openai(tools: list[Any]) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            },
        }
        for t in tools
    ]


class LiteLLMProxyProvider(BaseLLMProvider):
    """Universal provider that routes all requests through a LiteLLM proxy."""

    name = "litellm"

    def __init__(self, base_url: str, api_key: str = "dummy") -> None:
        self._base_url = base_url.rstrip("/")
        self._client = AsyncOpenAI(api_key=api_key, base_url=f"{self._base_url}/v1")
        self._http = httpx.AsyncClient(base_url=self._base_url, timeout=10)
        self._known_models: list[str] = []

    def get_default_model(self) -> str:
        return "claude-sonnet-4-5"

    async def list_models(self) -> list[str]:
        """Fetch available model IDs from the proxy."""
        try:
            resp = await self._http.get("/v1/models")
            resp.raise_for_status()
            data = resp.json()
            models = [m["id"] for m in data.get("data", [])]
            self._known_models = [m for m in models if not m.endswith("*")]
            return self._known_models
        except Exception as e:
            logger.warning("Failed to fetch model list from proxy", error=str(e))
            return self._known_models or [self.get_default_model()]

    async def complete(self, request: LLMRequest) -> LLMResponse:
        messages = _messages_to_openai(request.messages)
        if request.system_prompt:
            messages = [{"role": "system", "content": request.system_prompt}] + messages

        kwargs: dict[str, Any] = dict(
            model=request.model,
            messages=messages,
            temperature=request.temperature,
        )
        if request.tools:
            kwargs["tools"] = _tools_to_openai(request.tools)
            kwargs["tool_choice"] = "auto"

        try:
            response = await self._client.chat.completions.create(**kwargs)
        except openai_lib.AuthenticationError as e:
            raise LLMAuthError(str(e)) from e
        except openai_lib.RateLimitError as e:
            raise LLMRateLimitError(str(e)) from e
        except openai_lib.APITimeoutError as e:
            raise LLMTimeoutError(str(e)) from e
        except openai_lib.APIError as e:
            raise LLMError(str(e)) from e

        choice = response.choices[0]
        message = choice.message
        text_content = message.content or ""
        tool_calls = []
        if message.tool_calls:
            for tc in message.tool_calls:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                tool_calls.append({"id": tc.id, "name": tc.function.name, "input": args})

        usage = response.usage
        return LLMResponse(
            content=text_content,
            tool_calls=tool_calls,
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
            model=response.model,
            stop_reason=choice.finish_reason or "stop",
        )

    async def stream(self, request: LLMRequest) -> AsyncIterator[StreamDelta]:
        messages = _messages_to_openai(request.messages)
        if request.system_prompt:
            messages = [{"role": "system", "content": request.system_prompt}] + messages

        kwargs: dict[str, Any] = dict(
            model=request.model,
            messages=messages,
            temperature=request.temperature,
            stream=True,
            stream_options={"include_usage": True},
        )
        if request.tools:
            kwargs["tools"] = _tools_to_openai(request.tools)
            kwargs["tool_choice"] = "auto"

        try:
            tool_deltas: dict[int, ToolCallDelta] = {}
            input_tokens = 0
            output_tokens = 0

            async with await self._client.chat.completions.create(**kwargs) as stream:
                async for chunk in stream:
                    if chunk.usage:
                        input_tokens = chunk.usage.prompt_tokens or 0
                        output_tokens = chunk.usage.completion_tokens or 0

                    if not chunk.choices:
                        continue

                    delta = chunk.choices[0].delta

                    if delta.content:
                        yield StreamDelta(text=delta.content)

                    if delta.tool_calls:
                        for tc_chunk in delta.tool_calls:
                            idx = tc_chunk.index
                            if idx not in tool_deltas:
                                tool_deltas[idx] = ToolCallDelta(index=idx)
                                if tc_chunk.id:
                                    tool_deltas[idx].id = tc_chunk.id
                                if tc_chunk.function and tc_chunk.function.name:
                                    tool_deltas[idx].name = tc_chunk.function.name
                                yield StreamDelta(
                                    is_tool_start=True,
                                    tool_call_id=tc_chunk.id or "",
                                    tool_name=tc_chunk.function.name if tc_chunk.function else "",
                                )
                            if tc_chunk.function and tc_chunk.function.arguments:
                                tool_deltas[idx].input_json += tc_chunk.function.arguments

                    finish = chunk.choices[0].finish_reason
                    if finish in ("tool_calls", "stop", "length"):
                        for td in tool_deltas.values():
                            try:
                                tool_input = json.loads(td.input_json or "{}")
                            except json.JSONDecodeError:
                                tool_input = {}
                            yield StreamDelta(
                                tool_call_id=td.id or "",
                                tool_name=td.name or "",
                                tool_input=tool_input,
                            )
                        tool_deltas = {}

            yield StreamDelta(is_done=True, input_tokens=input_tokens, output_tokens=output_tokens)

        except openai_lib.AuthenticationError as e:
            raise LLMAuthError(str(e)) from e
        except openai_lib.RateLimitError as e:
            raise LLMRateLimitError(str(e)) from e
        except openai_lib.APITimeoutError as e:
            raise LLMTimeoutError(str(e)) from e
        except openai_lib.APIError as e:
            raise LLMError(str(e)) from e

    async def health_check(self) -> bool:
        try:
            models = await self.list_models()
            return len(models) > 0
        except Exception:
            return False
