"""Prompt template loader — reads .md files from this directory."""

from pathlib import Path
from functools import lru_cache

_DIR = Path(__file__).parent


@lru_cache(maxsize=16)
def load_prompt(name: str) -> str:
    """Load a prompt template by name (without extension)."""
    path = _DIR / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"Prompt template not found: {path}")
    return path.read_text(encoding="utf-8").strip()
