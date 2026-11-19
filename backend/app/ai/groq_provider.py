"""Groq provider — streaming + tool calling."""
from __future__ import annotations

import json
from typing import Any, AsyncIterator

from groq import AsyncGroq

from app.ai.provider_base import BaseProvider, ChatDelta, Message, ToolCall
from app.config.settings import get_settings


class GroqProvider(BaseProvider):
    name = "groq"

    def __init__(self, api_key: str | None = None, model: str | None = None):
        settings = get_settings()
        self._api_key = api_key or settings.groq_api_key
        self._model = model or settings.groq_model
        if not self._api_key:
            raise ValueError("GROQ_API_KEY missing — set NOT_GROQ_API_KEY in .env")
        self._client = AsyncGroq(api_key=self._api_key)

    def _to_groq_messages(self, messages: list[Message]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for m in messages:
            entry: dict[str, Any] = {"role": m.role, "content": m.content}
            if m.tool_call_id:
                entry["tool_call_id"] = m.tool_call_id
            if m.name:
                entry["name"] = m.name
            out.append(entry)
        return out

    async def chat(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> Message:
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": self._to_groq_messages(messages),
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        resp = await self._client.chat.completions.create(**kwargs)
        choice = resp.choices[0].message

        tool_calls: list[ToolCall] = []
        if choice.tool_calls:
            for tc in choice.tool_calls:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                tool_calls.append(ToolCall(id=tc.id, name=tc.function.name, arguments=args))

        if tool_calls:
            # Serialize tool calls back into the message content for the loop
            return Message(
                role="assistant",
                content=choice.content or "",
                tool_name=tool_calls[0].name,
                name=json.dumps([{"id": t.id, "name": t.name, "arguments": t.arguments} for t in tool_calls]),
            )
        return Message(role="assistant", content=choice.content or "")

    async def stream_chat(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> AsyncIterator[ChatDelta]:
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": self._to_groq_messages(messages),
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        stream = await self._client.chat.completions.create(**kwargs)

        # Accumulate tool calls across chunks
        tool_acc: dict[int, dict[str, Any]] = {}

        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            finish = chunk.choices[0].finish_reason

            text_piece = delta.content or ""
            tc_pieces: list[ToolCall] = []

            if getattr(delta, "tool_calls", None):
                for tc in delta.tool_calls:
                    idx = tc.index if tc.index is not None else 0
                    slot = tool_acc.setdefault(idx, {
                        "id": "", "name": "", "arguments": ""
                    })
                    if tc.id:
                        slot["id"] = tc.id
                    if tc.function:
                        if tc.function.name:
                            slot["name"] = tc.function.name
                        if tc.function.arguments:
                            slot["arguments"] += tc.function.arguments

            if finish:
                # Flush accumulated tool calls
                for slot in tool_acc.values():
                    try:
                        parsed_args = json.loads(slot["arguments"] or "{}")
                    except json.JSONDecodeError:
                        parsed_args = {}
                    tc_pieces.append(ToolCall(
                        id=slot["id"] or "call_unknown",
                        name=slot["name"] or "unknown",
                        arguments=parsed_args,
                    ))

            if text_piece or tc_pieces or finish:
                yield ChatDelta(
                    content=text_piece,
                    tool_calls=tc_pieces,
                    finish_reason=finish,
                )