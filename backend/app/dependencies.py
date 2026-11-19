from functools import lru_cache
from app.config.settings import settings

@lru_cache
def get_settings():
    return settings

def get_db():
    from app.db.connection import get_connection
    return get_connection()

def get_ai():
    from app.ai.groq_provider import GroqProvider
    return GroqProvider()

def get_search():
    from app.search.engine import SearchEngine
    return SearchEngine()
