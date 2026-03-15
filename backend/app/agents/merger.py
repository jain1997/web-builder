"""
Merger Agent — unifies parallel Stylist + Writer outputs.

All merges are now fully deterministic (no LLM call).

Merge strategy when both stylist and writer modified the same file:
  - Take stylist's version as the base  (better Tailwind classes / structure)
  - Extract className values from stylist and apply them onto writer's text content
  - Result: writer's copy + stylist's Tailwind classes
"""

from __future__ import annotations

import re
from app.agents.state import AgentState


_CLASS_RE = re.compile(r'className="([^"]*)"')


def _apply_classnames(writer_code: str, stylist_code: str) -> str:
    """
    Overlay Tailwind className values from stylist_code onto writer_code.

    Iterates through className="..." occurrences positionally.
    When stylist has a richer class string for the same element, use it.
    Falls back to writer's original class when stylist has none at that position.
    """
    stylist_classes = _CLASS_RE.findall(stylist_code)
    writer_classes  = _CLASS_RE.findall(writer_code)

    if not stylist_classes:
        return writer_code  # stylist added nothing — keep writer as-is

    result = writer_code
    # Walk through matched pairs and replace positionally
    for w_cls, s_cls in zip(writer_classes, stylist_classes):
        if w_cls != s_cls and s_cls:
            # Replace first occurrence of this exact class string
            result = result.replace(f'className="{w_cls}"', f'className="{s_cls}"', 1)

    return result


async def merger_node(state: AgentState) -> dict:
    """Unify parallel Stylist + Writer outputs — fully deterministic, no LLM."""

    stylist_files = state.get("stylist_files", {})
    writer_files  = state.get("writer_files", {})
    base_files    = state.get("generated_files", {})

    # ── Fast paths (only one branch ran) ────────────────────────────
    if not stylist_files and not writer_files:
        return {"current_step": ["Merger: no changes ✓"]}

    if stylist_files and not writer_files:
        return {
            "generated_files": {**base_files, **stylist_files},
            "current_step": ["Merger: applied styles ✓"],
        }

    if writer_files and not stylist_files:
        return {
            "generated_files": {**base_files, **writer_files},
            "current_step": ["Merger: applied content ✓"],
        }

    # ── Both ran — deterministic merge per file ──────────────────────
    all_paths = set(stylist_files) | set(writer_files)
    output_files: dict[str, str] = {}

    for path in all_paths:
        s_code = stylist_files.get(path, base_files.get(path, ""))
        w_code = writer_files.get(path,  base_files.get(path, ""))

        if s_code == w_code:
            output_files[path] = s_code
        elif not w_code:
            output_files[path] = s_code
        elif not s_code:
            output_files[path] = w_code
        else:
            # Apply stylist's Tailwind classes onto writer's text content
            print(f"[Merger] Deterministic merge for {path}")
            output_files[path] = _apply_classnames(w_code, s_code)

    return {
        "generated_files": {**base_files, **output_files},
        "current_step": ["Merger: unified ✓"],
    }
