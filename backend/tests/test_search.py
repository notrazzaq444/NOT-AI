import pytest
from app.search.engine import SearchEngine

@pytest.mark.asyncio
async def test_search_requires_provider_key(monkeypatch):
    from app.config import settings as settings_module
    monkeypatch.setattr(settings_module.settings, "tavily_api_key", "")
    monkeypatch.setattr(settings_module.settings, "brave_api_key", "")
    with pytest.raises(RuntimeError):
        await SearchEngine().search("test")
