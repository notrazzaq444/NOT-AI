import httpx
from app.config.settings import settings

class BraveClient:
    async def search(self, query: str, max_results: int = 5):
        if not settings.brave_api_key:
            raise RuntimeError("BRAVE_API_KEY is missing.")
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(
                "https://api.search.brave.com/res/v1/web/search",
                params={"q": query, "count": max_results},
                headers={"X-Subscription-Token": settings.brave_api_key},
            )
            response.raise_for_status()
            return response.json()
