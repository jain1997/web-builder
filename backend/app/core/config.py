"""Application configuration loaded from environment variables with validation."""

import sys
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings


# .env lives at backend root
_env_path = Path(__file__).resolve().parent.parent.parent / ".env"
_default_db = str(Path(__file__).resolve().parent.parent.parent / "data" / "agentic.db")


class Settings(BaseSettings):
    """Central configuration — validated at startup."""

    model_config = {"env_file": str(_env_path), "env_file_encoding": "utf-8", "extra": "ignore"}

    # ── LLM ───────────────────────────────────────────────────────
    OPENAI_API_KEY: str = ""
    LLM_PROVIDER: str = "openai"
    LLM_MODEL: str = "gpt-5.1"
    LLM_MODEL_SMALL: str = "gpt-5-mini-2025-08-07"

    # ── CORS ──────────────────────────────────────────────────────
    CORS_ORIGINS: str = "http://localhost:3000"

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse CORS_ORIGINS as comma-separated string or JSON list."""
        raw = self.CORS_ORIGINS.strip()
        if raw.startswith("["):
            import json
            return json.loads(raw)
        return [o.strip() for o in raw.split(",") if o.strip()]

    # ── Image generation ─────────────────────────────────────────
    IMAGE_PROVIDER: str = "openai"  # "openai" or "ollama"
    IMAGE_MODEL: str = "gpt-image-1"  # OpenAI: gpt-image-1 | Ollama: x/flux2-klein:latest
    IMAGE_SIZE: str = "1024x1024"  # OpenAI image size
    IMAGE_QUALITY: str = "medium"  # OpenAI: low, medium, high
    OLLAMA_BASE_URL: str = "http://localhost:11434"

    # ── Redis + Database ──────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"
    DATABASE_PATH: str = _default_db
    SESSION_CACHE_TTL: int = 3600

    # ── Image storage ───────────────────────────────────────────────
    IMAGE_STORAGE_PATH: str = str(Path(__file__).resolve().parent.parent.parent / "data" / "images")
    PUBLIC_URL: str = "http://localhost:8000"

    # ── Optional: WebSocket auth key (empty = no auth) ────────────
    WS_AUTH_KEY: str = ""

    @field_validator("OPENAI_API_KEY")
    @classmethod
    def _check_api_key(cls, v: str) -> str:
        if not v:
            print(
                "\n[FATAL] OPENAI_API_KEY is not set. "
                "Add it to backend/.env or export it as an environment variable.\n",
                file=sys.stderr,
            )
            sys.exit(1)
        return v


settings = Settings()
