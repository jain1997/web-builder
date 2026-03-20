"""
SQLite Database — persistent conversation history and file snapshots.

Uses a shared connection pool (single WAL-mode connection) instead of
opening/closing per query. aiosqlite serializes writes internally.

Schema is auto-created on first connection.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator

import aiosqlite

from app.core.config import settings
from app.core.enums import Intent
from app.core.logger import get_logger

log = get_logger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id          TEXT PRIMARY KEY,
    project     TEXT DEFAULT '',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS turns (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      TEXT NOT NULL REFERENCES sessions(id),
    prompt          TEXT NOT NULL,
    intent          TEXT NOT NULL DEFAULT 'create',
    plan            TEXT DEFAULT '',
    files_touched   TEXT DEFAULT '[]',
    errors          TEXT DEFAULT '[]',
    fix_summary     TEXT DEFAULT '',
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS file_snapshots (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    turn_id     INTEGER NOT NULL REFERENCES turns(id),
    session_id  TEXT NOT NULL,
    file_path   TEXT NOT NULL,
    content     TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_turns_session ON turns(session_id);
CREATE INDEX IF NOT EXISTS idx_snapshots_session_path ON file_snapshots(session_id, file_path);
CREATE INDEX IF NOT EXISTS idx_snapshots_turn ON file_snapshots(turn_id);
"""

# ── Shared connection ─────────────────────────────────────────────────

_conn: aiosqlite.Connection | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def init_db() -> None:
    """Create tables and open the shared connection."""
    global _conn
    Path(settings.DATABASE_PATH).parent.mkdir(parents=True, exist_ok=True)
    _conn = await aiosqlite.connect(settings.DATABASE_PATH)
    _conn.row_factory = aiosqlite.Row
    await _conn.execute("PRAGMA journal_mode=WAL")
    await _conn.execute("PRAGMA foreign_keys=ON")
    await _conn.executescript(_SCHEMA)
    await _conn.commit()
    log.info(f"Database initialized → {settings.DATABASE_PATH}")


async def close_db() -> None:
    """Close the shared connection (call on shutdown)."""
    global _conn
    if _conn:
        await _conn.close()
        _conn = None


@asynccontextmanager
async def _get_db() -> AsyncIterator[aiosqlite.Connection]:
    """
    Return the shared connection. Falls back to a fresh connection
    if the pool isn't initialized (e.g. during tests).
    """
    global _conn
    if _conn is not None:
        yield _conn
    else:
        db = await aiosqlite.connect(settings.DATABASE_PATH)
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA foreign_keys=ON")
        try:
            yield db
        finally:
            await db.close()


# ── Sessions ──────────────────────────────────────────────────────────

async def ensure_session(session_id: str) -> dict:
    """Get or create a session record."""
    async with _get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        )
        row = await cursor.fetchone()
        if row:
            return dict(row)

        now = _now()
        await db.execute(
            "INSERT INTO sessions (id, project, created_at, updated_at) VALUES (?, '', ?, ?)",
            (session_id, now, now),
        )
        await db.commit()
        return {"id": session_id, "project": "", "created_at": now, "updated_at": now}


async def update_session_project(session_id: str, project: str) -> None:
    async with _get_db() as db:
        await db.execute(
            "UPDATE sessions SET project = ?, updated_at = ? WHERE id = ?",
            (project[:200], _now(), session_id),
        )
        await db.commit()


# ── Turns ─────────────────────────────────────────────────────────────

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
    Persist a completed pipeline turn + snapshot all generated files.
    Returns the turn_id for reference.
    """
    now = _now()
    async with _get_db() as db:
        # Ensure session exists
        cursor = await db.execute("SELECT id FROM sessions WHERE id = ?", (session_id,))
        if not await cursor.fetchone():
            await db.execute(
                "INSERT INTO sessions (id, project, created_at, updated_at) VALUES (?, '', ?, ?)",
                (session_id, now, now),
            )

        # Insert turn
        cursor = await db.execute(
            """INSERT INTO turns (session_id, prompt, intent, plan, files_touched, errors, fix_summary, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                session_id,
                prompt[:500],
                intent,
                plan[:500],
                json.dumps(files_touched),
                json.dumps([e[:300] for e in errors]),
                fix_summary[:300],
                now,
            ),
        )
        turn_id = cursor.lastrowid

        # Snapshot every generated file (skip images — too large for SQLite)
        if generated_files:
            snapshots = [
                (turn_id, session_id, path, content, now)
                for path, content in generated_files.items()
                if not content.startswith("data:image/")
            ]
            if snapshots:
                await db.executemany(
                    """INSERT INTO file_snapshots (turn_id, session_id, file_path, content, created_at)
                       VALUES (?, ?, ?, ?, ?)""",
                    snapshots,
                )

        # Update project description from first successful create/modify
        if intent in (Intent.CREATE, Intent.MODIFY) and not errors:
            cursor = await db.execute(
                "SELECT project FROM sessions WHERE id = ?", (session_id,)
            )
            row = await cursor.fetchone()
            if row and not row[0]:
                await db.execute(
                    "UPDATE sessions SET project = ?, updated_at = ? WHERE id = ?",
                    (plan[:200], now, session_id),
                )

        await db.execute(
            "UPDATE sessions SET updated_at = ? WHERE id = ?", (now, session_id)
        )
        await db.commit()

    log.info(f"Saved turn #{turn_id} [{intent}] → session {session_id[:8]}")
    return turn_id


# ── Query: planner context ────────────────────────────────────────────

async def get_planner_context(session_id: str, max_turns: int = 8) -> str:
    """
    Build a compact text summary of recent turns for the planner.
    Reads from SQLite — the authoritative conversation history.
    """
    async with _get_db() as db:
        # Session metadata
        cursor = await db.execute(
            "SELECT project FROM sessions WHERE id = ?", (session_id,)
        )
        session = await cursor.fetchone()
        if not session:
            return ""

        # Recent turns
        cursor = await db.execute(
            """SELECT prompt, intent, plan, files_touched, errors, fix_summary
               FROM turns WHERE session_id = ?
               ORDER BY id DESC LIMIT ?""",
            (session_id, max_turns),
        )
        rows = await cursor.fetchall()

    if not rows:
        return ""

    lines = ["SESSION MEMORY (last turns):"]
    if session["project"]:
        lines.append(f"Project: {session['project']}")

    # Rows are newest-first, reverse for chronological display
    for i, t in enumerate(reversed(rows), 1):
        files = json.loads(t["files_touched"])
        file_str = ", ".join(files[:4]) + (f" (+{len(files)-4} more)" if len(files) > 4 else "")
        errors = json.loads(t["errors"])

        label = "repair" if errors else t["intent"]
        prompt_short = t["prompt"][:80].replace("\n", " ")

        lines.append(f'Turn {i} [{label}]: "{prompt_short}"')
        if file_str:
            lines.append(f"  → files: {file_str}")
        if errors:
            lines.append(f"  → error: {errors[0][:120]}")
        if t["fix_summary"]:
            lines.append(f"  → fixed: {t['fix_summary']}")

    return "\n".join(lines)


# ── Query: file history for file_generator ────────────────────────────

async def get_file_context(session_id: str, file_path: str) -> str:
    """
    Return error + fix history for a specific file.
    Helps the file_generator avoid repeating past mistakes.
    """
    async with _get_db() as db:
        # Use JSON functions to avoid LIKE injection
        cursor = await db.execute(
            """SELECT t.errors, t.fix_summary
               FROM turns t, json_each(t.files_touched) AS jf
               WHERE t.session_id = ? AND jf.value = ?
                     AND t.errors != '[]'
               ORDER BY t.id DESC LIMIT 5""",
            (session_id, file_path),
        )
        rows = await cursor.fetchall()

    if not rows:
        return ""

    lines = [f"FILE HISTORY for {file_path}:"]
    for t in reversed(rows):
        errors = json.loads(t["errors"])
        err = errors[0][:120].replace("\n", " ") if errors else ""
        fix = (t["fix_summary"] or "")[:120]
        lines.append(f'  Past error: "{err}"')
        if fix:
            lines.append(f'  Was fixed by: "{fix}"')

    return "\n".join(lines)


# ── Query: previous file snapshot (for smarter edits) ─────────────────

async def get_previous_file(session_id: str, file_path: str) -> str | None:
    """
    Return the most recent snapshot of a file from a prior turn.
    Used by file_generator to see the ACTUAL previous code — not a summary.
    This enables precise, targeted edits instead of full rewrites.
    """
    async with _get_db() as db:
        cursor = await db.execute(
            """SELECT content FROM file_snapshots
               WHERE session_id = ? AND file_path = ?
               ORDER BY id DESC LIMIT 1""",
            (session_id, file_path),
        )
        row = await cursor.fetchone()
        return row[0] if row else None
