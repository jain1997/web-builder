"""
Session Memory — persistent JSON-backed store for conversation history.

One JSON file per session:  data/sessions/{session_id}.json

Stored per turn:
  - user prompt, intent, plan
  - files touched (paths only, not code — code lives in the state)
  - errors encountered
  - fix summary (from validator)

Why this helps auto-repair:
  When the frontend sends "Fix these rendering errors: Element type is invalid…Header",
  the planner previously had zero context about what was built.
  With memory it knows: "This is a DLC Bank website, turn 1 generated Header.tsx as a
  navigation component imported by App.tsx, and the error pattern matches a default-export
  mismatch." → routes to intent=modify with exactly the right files.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ── Storage path ─────────────────────────────────────────────────────────────
_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "sessions"
_MAX_TURNS = 10   # keep last N turns to stay within LLM context limits


# ── Helpers ───────────────────────────────────────────────────────────────────
def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _session_path(session_id: str) -> Path:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    # Sanitise — only allow alphanumeric + hyphens/underscores
    safe_id = "".join(c for c in session_id if c.isalnum() or c in "-_")[:64]
    return _DATA_DIR / f"{safe_id}.json"


# ── Public API ────────────────────────────────────────────────────────────────
def load(session_id: str) -> dict:
    """Return the full session dict, or an empty skeleton if not found."""
    path = _session_path(session_id)
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception as e:
            log.warning(f"Memory load failed for {session_id}: {e}")
    return {"session_id": session_id, "created_at": _now(), "updated_at": _now(),
            "project": "", "turns": []}


def save_turn(
    session_id: str,
    *,
    prompt: str,
    intent: str,
    plan: str,
    files_touched: list[str],
    errors: list[str],
    fix_summary: str,
) -> None:
    """Append a completed pipeline turn to the session file."""
    mem = load(session_id)

    turn: dict[str, Any] = {
        "at":            _now(),
        "prompt":        prompt[:200],   # truncate long auto-fix prompts
        "intent":        intent,
        "plan":          plan[:300],
        "files_touched": files_touched,
        "errors":        [e[:300] for e in errors],
        "fix_summary":   fix_summary[:300],
    }

    # Infer/update project description from the first non-fix create/modify turn
    if not mem["project"] and intent in ("create", "modify") and not errors:
        mem["project"] = plan[:120]

    mem["turns"].append(turn)
    mem["turns"] = mem["turns"][-_MAX_TURNS:]   # keep last N turns
    mem["updated_at"] = _now()

    path = _session_path(session_id)
    try:
        path.write_text(json.dumps(mem, indent=2))
    except Exception as e:
        log.warning(f"Memory save failed for {session_id}: {e}")


def get_planner_context(session_id: str) -> str:
    """
    Return a compact text block for the planner's context window.

    Example output:
        SESSION MEMORY (last 3 turns):
        Project: DLC Bank website with multi-page navigation
        Turn 1 [create]: "generate bank website"
          → files: App.tsx, components/Header.tsx, components/Footer.tsx (+3 more)
        Turn 2 [repair]: Error "Element type is invalid…Header"
          → fixed: corrected default export in components/Header.tsx
        Turn 3 [modify]: "add a dark mode toggle"
          → files: components/Header.tsx
    """
    mem = load(session_id)
    turns = mem.get("turns", [])
    if not turns:
        return ""

    lines = ["SESSION MEMORY (last turns):"]
    if mem.get("project"):
        lines.append(f"Project: {mem['project']}")

    for i, t in enumerate(turns, 1):
        files = t.get("files_touched", [])
        file_str = ", ".join(files[:4]) + (f" (+{len(files)-4} more)" if len(files) > 4 else "")

        label = "repair" if t.get("errors") else t.get("intent", "?")
        prompt_short = t["prompt"][:80].replace("\n", " ")

        lines.append(f'Turn {i} [{label}]: "{prompt_short}"')
        if file_str:
            lines.append(f"  → files: {file_str}")
        if t.get("errors"):
            err_short = t["errors"][0][:120].replace("\n", " ")
            lines.append(f"  → error: {err_short}")
        if t.get("fix_summary"):
            lines.append(f"  → fixed: {t['fix_summary']}")

    return "\n".join(lines)


def get_file_context(session_id: str, file_path: str) -> str:
    """
    Return the error + fix history for a specific file.
    Used by file_generator to avoid repeating past mistakes.

    Example output:
        FILE HISTORY for components/Header.tsx:
        Turn 2: error "Element type is invalid" → fix: corrected default export
    """
    mem = load(session_id)
    turns = mem.get("turns", [])

    relevant = [
        t for t in turns
        if file_path in t.get("files_touched", []) and t.get("errors")
    ]
    if not relevant:
        return ""

    lines = [f"FILE HISTORY for {file_path}:"]
    for i, t in enumerate(relevant, 1):
        err = t["errors"][0][:120].replace("\n", " ") if t.get("errors") else ""
        fix = t.get("fix_summary", "")[:120]
        lines.append(f"  Past error: \"{err}\"")
        if fix:
            lines.append(f"  Was fixed by: \"{fix}\"")

    return "\n".join(lines)
