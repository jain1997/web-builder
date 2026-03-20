"""
Session Memory — facade over Redis (active state) + SQLite (history).

Redis handles:
  - Active session cache (fast reads during pipeline)
  - Session file state (current generated files)
  - TTL-based expiry (1 hour default)

SQLite handles:
  - Full conversation turn history
  - File snapshots per turn (actual code, not just paths)
  - Enables file_generator to see previous code for smarter edits
"""

from __future__ import annotations

from app.core import redis_client as rc
from app.core import database as db
from app.core.logger import get_logger

log = get_logger(__name__)


# ── Session lifecycle ─────────────────────────────────────────────────

async def start_session(session_id: str) -> dict:
    """Ensure session exists in both Redis and SQLite."""
    # Check Redis first (fast path)
    cached = await rc.get_session(session_id)
    if cached:
        await rc.touch_session(session_id)
        return cached

    # Fall back to SQLite
    session = await db.ensure_session(session_id)

    # Warm the Redis cache
    await rc.save_session(session_id, session)
    return session


async def cache_files(session_id: str, files: dict[str, str]) -> None:
    """Cache current file state in Redis for quick access."""
    await rc.save_session_files(session_id, files)


async def get_cached_files(session_id: str) -> dict[str, str] | None:
    """Fetch cached files from Redis."""
    return await rc.get_session_files(session_id)


# ── Turn persistence (SQLite) ────────────────────────────────────────

async def save_turn(
    session_id: str,
    *,
    prompt: str,
    intent: str,
    plan: str,
    files_touched: list[str],
    errors: list[str],
    fix_summary: str,
    generated_files: dict[str, str] | None = None,
) -> int:
    """
    Persist a completed turn to SQLite and update Redis cache.
    Also snapshots all generated code files for future reference.
    """
    turn_id = await db.save_turn(
        session_id,
        prompt=prompt,
        intent=intent,
        plan=plan,
        files_touched=files_touched,
        errors=errors,
        fix_summary=fix_summary,
        generated_files=generated_files,
    )

    # Update Redis with latest files
    if generated_files:
        await rc.save_session_files(session_id, generated_files)

    return turn_id


# ── Context queries (read from SQLite) ────────────────────────────────

async def get_planner_context(session_id: str) -> str:
    """Compact turn summary for the planner's context window."""
    return await db.get_planner_context(session_id)


async def get_file_context(session_id: str, file_path: str) -> str:
    """Error + fix history for a specific file."""
    return await db.get_file_context(session_id, file_path)


async def get_previous_file(session_id: str, file_path: str) -> str | None:
    """
    Fetch the most recent snapshot of a file from a prior turn.
    Enables the file_generator to make precise edits instead of full rewrites.
    """
    return await db.get_previous_file(session_id, file_path)
