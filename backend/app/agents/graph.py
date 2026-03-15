"""
LangGraph State-Graph — Parallel File Generation Pipeline.

  START → planner → fan-out via Send ──┐
                  ├─ file_generator(App.tsx)         ─┐
                  ├─ file_generator(components/A.tsx) ─┤  (all parallel)
                  └─ file_generator(components/B.tsx) ─┘
                            ↓ (all branches converge)
                        assembler → validator → END (or retry)
"""

from __future__ import annotations

from langgraph.graph import END, StateGraph
from langgraph.types import Send

from app.agents.planner import planner_node
from app.agents.file_generator import file_generator_node
from app.agents.validator import validator_node
from app.agents.state import AgentState
from app.core.logger import get_logger, Timer

log = get_logger(__name__)


# ── Assembler ────────────────────────────────────────────────────────
async def assembler_node(state: AgentState) -> dict:
    t     = Timer()
    parts = state.get("generated_file_parts", [])
    merged: dict[str, str] = {}
    for part in parts:
        merged.update(part)

    existing = state.get("generated_files", {})
    final    = {**existing, **merged}

    log.info(f"Assembled {len(merged)} file(s) in {t.elapsed()}s → {list(merged.keys())}")
    return {
        "generated_files":      final,
        "generated_file_parts": [],
        "current_step":         [f"Assembler: {len(merged)} file(s) ready ✓"],
    }


# ── Routing ──────────────────────────────────────────────────────────
def route_planner(state: AgentState):
    intent    = state.get("intent", "create")
    file_plan = state.get("file_plan", [])

    if intent == "fix" or not file_plan:
        log.info(f"route_planner → assembler (intent={intent}, files={len(file_plan)})")
        return "assembler"

    log.info(f"route_planner → Send x{len(file_plan)} parallel generators")
    return [
        Send("file_generator", {**state, "current_file": file_info})
        for file_info in file_plan
    ]


def route_validator(state: AgentState) -> str:
    errors      = state.get("compilation_errors", [])
    retry_count = state.get("retry_count", 0)

    if not errors:
        log.info("route_validator → END (no errors)")
        return END
    if retry_count < 3:
        log.warning(f"route_validator → planner (retry {retry_count + 1}/3, {len(errors)} error(s))")
        return "planner"
    log.error(f"route_validator → END (max retries reached with {len(errors)} unresolved error(s))")
    return END


# ── Graph ────────────────────────────────────────────────────────────
def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    graph.add_node("planner",        planner_node)
    graph.add_node("file_generator", file_generator_node)
    graph.add_node("assembler",      assembler_node)
    graph.add_node("validator",      validator_node)

    graph.set_entry_point("planner")
    graph.add_conditional_edges("planner", route_planner, ["file_generator", "assembler"])
    graph.add_edge("file_generator", "assembler")
    graph.add_edge("assembler", "validator")
    graph.add_conditional_edges("validator", route_validator)

    return graph.compile()


agent_graph = build_graph()
