"""Central configuration loader. Validates .env at startup."""
from __future__ import annotations

import os
from pathlib import Path
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = PROJECT_ROOT / "backend" / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_prefix="NOT_",
        case_sensitive=False,
        extra="ignore",
    )

    # Server
    host: str = "127.0.0.1"
    port: int = 8000
    env: str = "development"
    log_level: str = "INFO"

    # Paths
    data_dir: Path = PROJECT_ROOT / "data"
    db_path: Path = PROJECT_ROOT / "data" / "not.db"
    memory_dir: Path = PROJECT_ROOT / "data" / "memory"
    whisper_cache: Path = PROJECT_ROOT / "data" / "whisper"

    # AI
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"
    groq_tool_model: str = "openai/gpt-oss-120b"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-3-5-haiku-latest"

    # Gemini
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash-lite"

    # Search
    tavily_api_key: str = ""
    brave_api_key: str = ""
    search_primary: str = "tavily"
    search_fallback: str = "brave"

    # Voice
    whisper_model: str = "base"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"
    tts_default_voice_en: str = "en-US-AriaNeural"
    tts_default_voice_ur: str = "hi-IN-MadhurNeural"
    tts_rate: float = 1.0
    wake_word_enabled: bool = False
    wake_word_phrase: str = "hey not"
    
        # Fish Audio
    fish_api_key: str = ""
    fish_voice_id: str = ""

    # Automation
    allowed_file_roots: str = "~/Documents,~/Desktop"
    require_confirmation: bool = True
    allow_terminal: bool = False
    allow_install: bool = False

    # Memory
    memory_retention_days: int = 365
    short_term_turns: int = 12
    fact_save_requires_consent: bool = True
    
    # Firebase
    firebase_api_key: str = ""
    firebase_auth_domain: str = ""
    firebase_project_id: str = ""
    firebase_storage_bucket: str = ""
    firebase_messaging_sender_id: str = ""
    firebase_app_id: str = ""

    @field_validator("data_dir", "db_path", "memory_dir", "whisper_cache", mode="before")
    @classmethod
    def _resolve_path(cls, value: str | Path) -> Path:
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = (PROJECT_ROOT / path).resolve()
        return path

    def allowed_roots_list(self) -> list[Path]:
        roots = []
        for raw in self.allowed_file_roots.split(","):
            raw = raw.strip()
            if not raw:
                continue
            p = Path(raw).expanduser().resolve()
            if p.exists():
                roots.append(p)
        return roots

    def ensure_directories(self) -> None:
        for directory in (self.data_dir, self.memory_dir, self.whisper_cache):
            directory.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_directories()
    return settings