from openai import AsyncOpenAI
from app.config.settings import settings
from app.ai.provider_base import AbstractProvider

class OpenAIProvider(AbstractProvider):
    def __init__(self):
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is missing.")
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)

    async def chat(self, messages, **kwargs):
        result = await self.client.chat.completions.create(
            model=settings.openai_model,
            messages=messages,
            temperature=kwargs.get("temperature", 0.7),
        )
        return result.choices[0].message.content or ""

    async def close(self):
        await self.client.close()
