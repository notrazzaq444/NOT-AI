import httpx
from app.config.settings import settings

class TavilyClient:
    async def search(self, query: str, max_results: int = 5):
        if not settings.tavily_api_key:
            raise RuntimeError("TAVILY_API_KEY is missing.")
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                "https://api.tavily.com/search",
                json={"api_key": settings.tavily_api_key, "query": query,
                      "max_results": max_results, "include_answer": True},
            )
            response.raise_for_status()
            return response.json()

    async def extract(self, urls: list[str]):
        if not settings.tavily_api_key:
            raise RuntimeError("TAVILY_API_KEY is missing.")
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                "https://api.tavily.com/extract",
                json={"api_key": settings.tavily_api_key, "urls": urls},
            )
            response.raise_for_status()
            return response.json()
