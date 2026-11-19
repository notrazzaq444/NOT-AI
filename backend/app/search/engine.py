from app.config.settings import settings
from app.search.tavily_client import TavilyClient
from app.search.brave_client import BraveClient

class SearchEngine:
    async def search(self, query: str, max_results: int = 5):
        if settings.tavily_api_key:
            return await TavilyClient().search(query, max_results)
        if settings.brave_api_key:
            return await BraveClient().search(query, max_results)
        raise RuntimeError("Configure TAVILY_API_KEY or BRAVE_API_KEY for live web search.")
