"""
LangGraph agent state schema.

This TypedDict is the single source of truth flowing through the graph.
Every node reads from / writes to this state.
"""

from __future__ import annotations

import operator
from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage


class AgentState(TypedDict, total=False):
    """Shared state that flows through the LangGraph pipeline."""

    # ── Session / memory ────────────────────────────────────────────
    session_id: str      # frontend-generated UUID, persists in localStorage
    memory_context: str  # pre-built text summary injected into planner + file_generator

    # ── User input ──────────────────────────────────────────────────
    user_prompt: str
    intent: str          # "create" | "modify" | "fix"
    plan: str

    # ── Message history (append-only across nodes) ──────────────────
    messages: Annotated[list[BaseMessage], operator.add]

    # ── Planner output ───────────────────────────────────────────────
    # List of files the planner decided to create/modify, e.g.:
    # [{"path": "App.tsx", "description": "Root app that renders the form"},
    #  {"path": "components/JobForm.tsx", "description": "Form with all fields"}]
    file_plan: list[dict]

    # ── Parallel file generation (via LangGraph Send API) ────────────
    # Each file_generator node appends one {path: code} dict here.
    # operator.add accumulates results from all parallel branches.
    generated_file_parts: Annotated[list[dict], operator.add]

    # Per-generator context injected by Send — which file to generate.
    current_file: dict   # {"path": str, "description": str}

    # ── Final assembled output ───────────────────────────────────────
    generated_files: dict[str, str]   # filepath → source code

    # ── Feedback loop ────────────────────────────────────────────────
    compilation_errors: list[str]
    retry_count: int

    # ── Observability ────────────────────────────────────────────────
    current_step: Annotated[list[str], operator.add]

    # ── Legacy fields (kept for validator / backwards compat) ────────
    component_schema: dict
    styling_rules: dict
    needs_architect: bool
    needs_stylist: bool
    needs_writer: bool
    stylist_files: dict[str, str]
    writer_files: dict[str, str]
