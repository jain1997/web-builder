"""
LangGraph State-Graph — Parallel File + Image Generation Pipeline.

  START → planner → fan-out via Send ──┐
                  ├─ file_generator(App.tsx)         ─┐
                  ├─ file_generator(components/A.tsx) ─┤  (all parallel)
                  ├─ image_generator(images/hero.png) ─┤
                  └─ image_generator(images/bg.png)   ─┘
                            ↓ (all branches converge)
                        assembler → validator → END (or retry)
"""

from __future__ import annotations

import re

from langgraph.graph import END, StateGraph
from langgraph.types import Send

from app.agents.planner import planner_node
from app.agents.file_generator import file_generator_node
from app.agents.image_generator import image_generator_node
from app.agents.validator import validator_node
from app.agents.state import AgentState
from app.core.logger import get_logger, Timer

log = get_logger(__name__)


# ── Assembler ────────────────────────────────────────────────────────
async def assembler_node(state: AgentState) -> dict:
    t = Timer()

    # Merge code file parts
    parts = state.get("generated_file_parts", [])
    merged_files: dict[str, str] = {}
    for part in parts:
        merged_files.update(part)

    # Merge image parts
    image_parts = state.get("generated_image_parts", [])
    merged_images: dict[str, str] = {}
    for part in image_parts:
        merged_images.update(part)

    # Inline image data URIs into code — Sandpack can't fetch external URLs
    if merged_images:
        existing_code = state.get("generated_files", {})
        all_code = {**existing_code, **merged_files}

        for file_path, code in list(all_code.items()):
            # Only process code files, not image entries
            if file_path.startswith("images/"):
                continue
            for img_path, data_uri in merged_images.items():
                # Replace all variants: "/images/x.png", "images/x.png", '/images/x.png'
                code = code.replace(f'"/{img_path}"', f'"{data_uri}"')
                code = code.replace(f"'/{img_path}'", f"'{data_uri}'")
                code = code.replace(f'"{img_path}"', f'"{data_uri}"')
                code = code.replace(f"'{img_path}'", f"'{data_uri}'")
            if file_path in merged_files:
                merged_files[file_path] = code
            else:
                # Update existing file with inlined images
                all_code[file_path] = code
                merged_files[file_path] = code

    existing = state.get("generated_files", {})
    # Merge code files but exclude image entries (images/ paths) from the
    # file set sent to the frontend — Sandpack only needs .tsx/.ts files.
    final = {k: v for k, v in {**existing, **merged_files}.items() if not k.startswith("images/")}

    log.info(
        f"Assembled {len(merged_files)} file(s) + {len(merged_images)} image(s) "
        f"in {t.elapsed()}s → {list(merged_files.keys())}"
    )
    return {
        "generated_files":      final,
        "generated_file_parts": [],
        "generated_image_parts": [],
        "current_step": [
            f"Assembler: {len(merged_files)} file(s) + {len(merged_images)} image(s) ready ✓"
        ],
    }


# ── Routing ──────────────────────────────────────────────────────────
def route_planner(state: AgentState):
    intent     = state.get("intent", "create")
    file_plan  = state.get("file_plan", [])
    image_plan = state.get("image_plan", [])

    if intent == "fix" or (not file_plan and not image_plan):
        log.info(f"route_planner → assembler (intent={intent}, files={len(file_plan)}, images={len(image_plan)})")
        return "assembler"

    sends = []
    for file_info in file_plan:
        sends.append(Send("file_generator", {**state, "current_file": file_info}))
    for image_info in image_plan:
        sends.append(Send("image_generator", {**state, "current_image": image_info}))

    log.info(
        f"route_planner → Send x{len(file_plan)} files + x{len(image_plan)} images (parallel)"
    )
    return sends


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

    graph.add_node("planner",         planner_node)
    graph.add_node("file_generator",  file_generator_node)
    graph.add_node("image_generator", image_generator_node)
    graph.add_node("assembler",       assembler_node)
    graph.add_node("validator",       validator_node)

    graph.set_entry_point("planner")
    graph.add_conditional_edges(
        "planner", route_planner,
        ["file_generator", "image_generator", "assembler"],
    )
    graph.add_edge("file_generator",  "assembler")
    graph.add_edge("image_generator", "assembler")
    graph.add_edge("assembler", "validator")
    graph.add_conditional_edges("validator", route_validator)

    return graph.compile()


agent_graph = build_graph()
