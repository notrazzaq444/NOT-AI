"""Gemini provider - streaming + tool calling using google-genai SDK."""
from __future__ import annotations

import json
from typing import Any, AsyncIterator

from google import genai
from google.genai import types

from app.ai.provider_base import BaseProvider, ChatDelta, Message, ToolCall
from app.config.settings import get_settings


class GeminiProvider(BaseProvider):
    name = "gemini"

    def __init__(self, api_key: str | None = None, model: str | None = None):
        settings = get_settings()
        self._api_key = api_key or settings.gemini_api_key
        self._model = model or settings.gemini_model
        if not self._api_key:
            raise ValueError("GEMINI_API_KEY missing - set NOT_GEMINI_API_KEY in .env")
        self._client = genai.Client(api_key=self._api_key)

    def _to_gemini_contents(self, messages: list[Message]) -> list[types.Content]:
        """Convert our Message objects to Gemini Content objects."""
        contents = []
        for m in messages:
            if m.role == "system":
                continue
            elif m.role == "user":
                contents.append(types.Content(role="user", parts=[types.Part(text=m.content)]))
            elif m.role == "assistant":
                if m.name:
                    try:
                        tool_calls_data = json.loads(m.name)
                        parts = []
                        if m.content:
                            parts.append(types.Part(text=m.content))
                        for tc in tool_calls_data:
                            # thought_signature add karna zaroori hai Gemini 3.x ke liye
                            parts.append(types.Part(
                                function_call=types.FunctionCall(
                                    name=tc["name"],
                                    args=tc["arguments"]
                                ),
                                thought_signature="skip_thought_signature_validator"
                            ))
                        contents.append(types.Content(role="model", parts=parts))
                    except (json.JSONDecodeError, KeyError):
                        contents.append(types.Content(role="model", parts=[types.Part(text=m.content or "")]))
                else:
                    contents.append(types.Content(role="model", parts=[types.Part(text=m.content)]))
            elif m.role == "tool":
                # Gemini tool response ke liye user role use karta hai
                contents.append(types.Content(
                    role="user",
                    parts=[types.Part(
                        function_response=types.FunctionResponse(
                            name=m.name or m.tool_name or "unknown",
                            response={"result": m.content}
                        )
                    )]
                ))
        return contents

    async def chat(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> Message:
        system_prompt = ""
        for m in messages:
            if m.role == "system":
                system_prompt = m.content
                break

        contents = self._to_gemini_contents(messages)

        gemini_tools = None
        if tools:
            gemini_tools = []
            for tool in tools:
                func = tool["function"]
                gemini_tools.append(types.Tool(
                    function_declarations=[
                        types.FunctionDeclaration(
                            name=func["name"],
                            description=func.get("description", ""),
                            parameters=func.get("parameters", {})
                        )
                    ]
                ))

        config = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
            system_instruction=system_prompt if system_prompt else None,
            tools=gemini_tools if gemini_tools else None,
        )

        response = await self._client.aio.models.generate_content(
            model=self._model,
            contents=contents,
            config=config,
        )

        function_calls = []
        text_parts = []
        if response.candidates and response.candidates[0].content.parts:
            for part in response.candidates[0].content.parts:
                if part.function_call:
                    function_calls.append(ToolCall(
                        id=f"call_{part.function_call.name}",
                        name=part.function_call.name,
                        arguments=dict(part.function_call.args) if part.function_call.args else {}
                    ))
                elif part.text:
                    text_parts.append(part.text)

        if function_calls:
            return Message(
                role="assistant",
                content="".join(text_parts),
                tool_name=function_calls[0].name,
                name=json.dumps([
                    {"id": tc.id, "name": tc.name, "arguments": tc.arguments}
                    for tc in function_calls
                ]),
            )

        return Message(role="assistant", content="".join(text_parts))

    async def stream_chat(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> AsyncIterator[ChatDelta]:
        system_prompt = ""
        for m in messages:
            if m.role == "system":
                system_prompt = m.content
                break

        contents = self._to_gemini_contents(messages)

        gemini_tools = None
        if tools:
            gemini_tools = []
            for tool in tools:
                func = tool["function"]
                gemini_tools.append(types.Tool(
                    function_declarations=[
                        types.FunctionDeclaration(
                            name=func["name"],
                            description=func.get("description", ""),
                            parameters=func.get("parameters", {})
                        )
                    ]
                ))

        config = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
            system_instruction=system_prompt if system_prompt else None,
            tools=gemini_tools if gemini_tools else None,
        )

        response_stream = await self._client.aio.models.generate_content_stream(
            model=self._model,
            contents=contents,
            config=config,
        )

        accumulated_function_calls = []

        async for chunk in response_stream:
            if not chunk.candidates or not chunk.candidates[0].content.parts:
                continue

            for part in chunk.candidates[0].content.parts:
                if part.text:
                    yield ChatDelta(content=part.text, finish_reason=None)
                elif part.function_call:
                    accumulated_function_calls.append(ToolCall(
                        id=f"call_{part.function_call.name}",
                        name=part.function_call.name,
                        arguments=dict(part.function_call.args) if part.function_call.args else {}
                    ))

        if accumulated_function_calls:
            yield ChatDelta(
                content="",
                tool_calls=accumulated_function_calls,
                finish_reason="tool_calls"
            )
        else:
            yield ChatDelta(content="", tool_calls=[], finish_reason="stop")