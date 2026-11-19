"""Orchestrator - tool-call loop with streaming & memory."""
from __future__ import annotations
import asyncio
import json
import uuid
from typing import AsyncIterator
from app.ai.provider_base import BaseProvider, Message
from app.ai.tool_registry import TOOL_SCHEMAS, execute_tool
from app.config.constants import PERSONA
from app.memory.store import MemoryStore

LANG_NAMES = {
    "en": "English", "ur": "Urdu", "hi": "Hindi", 
    "ps": "Pashto", "mr": "Marathi", "ar": "Arabic", 
    "es": "Spanish", "fr": "French", "de": "German", "zh": "Chinese"
}

class Orchestrator:
    def __init__(self, provider: BaseProvider, max_tool_rounds: int = 3):
        self.provider = provider
        self.max_tool_rounds = max_tool_rounds
        self.memory = MemoryStore()

    async def run(self, history: list[Message], user_timezone: str = "UTC", user_language: str = "en") -> AsyncIterator[dict]:
        latest_user_msg = history[-1].content if history and history[-1].role == "user" else ""
        memories = await asyncio.to_thread(\n            self.memory.search_memory, latest_user_msg, n_results=3\n        )
        
        memory_context = ""
        if memories:
            memory_context = "\n\n**RELEVANT MEMORIES:**\n" + "\n".join(f"- {m}" for m in memories)

        # Strict Language Prompt
        lang_name = LANG_NAMES.get(user_language, "English")
        lang_prompt = f"\n\n**CRITICAL RULE:** You MUST reply ONLY in {lang_name}. Do NOT add translations in brackets. Do NOT use any other language."

        messages: list[Message] = [
            Message(role="system", content=PERSONA + memory_context + lang_prompt)
        ] + history

        for _ in range(self.max_tool_rounds + 1):
            accumulated_text = ""
            pending_tool_calls = []

            async for delta in self.provider.stream_chat(messages, tools=TOOL_SCHEMAS):
                if delta.content:
                    accumulated_text += delta.content
                    yield {"type": "token", "text": delta.content}
                for tc in delta.tool_calls:
                    pending_tool_calls.append(tc)

            if not pending_tool_calls:
                if accumulated_text.strip():
                    self.memory.add_memory(
                        text=f"User: {latest_user_msg}\nAI: {accumulated_text}",
                        metadata={"type": "conversation"},
                        mem_id=f"msg_{hash(latest_user_msg + accumulated_text)}"
                    )
                yield {"type": "done", "content": accumulated_text}
                return

            messages.append(Message(
                role="assistant", content=accumulated_text or "",
                name=json.dumps([{"id": tc.id, "name": tc.name, "arguments": tc.arguments} for tc in pending_tool_calls]),
            ))

            for tc in pending_tool_calls:
                if tc.name == "look_through_camera":
                    yield {"type": "camera_request", "prompt": tc.arguments.get("prompt", "Describe what is visible.")}
                    continue
                if tc.name == "get_current_time" and not tc.arguments.get("timezone"):
                    tc.arguments["timezone"] = user_timezone
                
                yield {"type": "tool_call", "name": tc.name, "args": tc.arguments}
                result = await asyncio.to_thread(execute_tool, tc.name, tc.arguments)
                yield {"type": "tool_result", "name": tc.name, "result": result}
                messages.append(Message(role="tool", content=result, tool_name=tc.name, tool_call_id=tc.id, name=tc.name))

        yield {"type": "done", "content": "Tool limit reached."}