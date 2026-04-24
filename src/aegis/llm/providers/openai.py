"""OpenAI provider (also used by Ollama)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import openai as openai_lib
from openai import AsyncOpenAI

from ...utils.errors import LLMAuthError, LLMError, LLMRateLimitError, LLMTimeoutError
from ...utils.logging import get_logger
from ..base import BaseLLMProvider
from ..types import LLMMessage, LLMRequest, LLMResponse, StreamDelta, ToolCallDelta

logger = get_logger(__name__)


def _messages_to_openai(messages: list[LLMMessage]) -> list[dict[str, Any]]:
    """Convert LLMMessages to OpenAI format."""
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
            result.append({"role": msg.role, "content": msg.content})
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


class OpenAIProvider(BaseLLMProvider):
    """OpenAI-compatible provider."""

    name = "openai"

    def __init__(self, api_key: str = "", base_url: str | None = None) -> None:
        kwargs: dict[str, Any] = {}
        if api_key:
            kwargs["api_key"] = api_key
        if base_url:
            kwargs["base_url"] = base_url
        self._client = AsyncOpenAI(**kwargs)

    def get_default_model(self) -> str:
        return "gpt-4.1"

    async def complete(self, request: LLMRequest) -> LLMResponse:
        messages = _messages_to_openai(request.messages)
        if request.system_prompt:
            messages = [{"role": "system", "content": request.system_prompt}] + messages

        kwargs: dict[str, Any] = dict(
            model=request.model,
            messages=messages,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
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
                tool_calls.append({
                    "id": tc.id,
                    "name": tc.function.name,
                    "input": args,
                })

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
            max_tokens=request.max_tokens,
            stream=True,
            stream_options={"include_usage": True},
        )
        if request.tools:
            kwargs["tools"] = _tools_to_openai(request.tools)
            kwargs["tool_choice"] = "auto"

        try:
            # Accumulate tool calls across chunks
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
                                # Signal tool start
                                yield StreamDelta(
                                    is_tool_start=True,
                                    tool_call_id=tc_chunk.id or "",
                                    tool_name=tc_chunk.function.name if tc_chunk.function else "",
                                )
                            if tc_chunk.function and tc_chunk.function.arguments:
                                tool_deltas[idx].input_json += tc_chunk.function.arguments

                    finish = chunk.choices[0].finish_reason
                    if finish in ("tool_calls", "stop", "length"):
                        # Emit completed tool calls
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
            await self._client.models.list()
            return True
        except Exception:
            return False
