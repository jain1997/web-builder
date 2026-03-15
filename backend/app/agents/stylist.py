"""UI/UX Stylist Agent."""

import json
from langchain_core.messages import SystemMessage
from app.agents.state import AgentState
from app.agents.utils import extract_json, retry_on_error
from app.core.llm import get_llm

STYLIST_SYSTEM_PROMPT = """\
You are a Tailwind CSS expert. Enhance the given React files with polished styling.
RULES:
- ONLY modify className values — do NOT change structure, logic, or text content.
- Tailwind only. No styled-jsx, no CSS imports.
- Respond ONLY with JSON: {"generated_files":{...},"styling_rules":{...}}
- No markdown fences.
"""

# Only pass these file types to stylist — configs/JSON are irrelevant
_STYLIST_EXTENSIONS = (".tsx", ".jsx", ".html")


@retry_on_error(retries=2)
async def stylist_node(state: AgentState) -> dict:
    llm = get_llm(temperature=0.2, model_tier="small")   # downgraded: small model is sufficient

    # Only send renderable files — drop package.json, tsconfig, etc.
    all_files = state.get("generated_files", {})
    relevant  = {p: c for p, c in all_files.items() if p.endswith(_STYLIST_EXTENSIONS)}
    files_str = json.dumps(relevant or all_files, indent=2)

    errors = state.get("compilation_errors", [])
    error_ctx = f"\n\nCURRENT ERRORS:\n{chr(10).join(errors)}" if errors else ""

    print(f"\n[Stylist] Enhancing {len(relevant)} file(s)...")

    # No full message history — stylist only needs the current file content
    response = await llm.ainvoke([
        SystemMessage(content=STYLIST_SYSTEM_PROMPT),
        SystemMessage(content=f"Files to style:\n{files_str}{error_ctx}"),
    ])

    print("[Stylist] Done.")
    data = extract_json(response.content)

    return {
        "stylist_files": data.get("generated_files", {}),
        "styling_rules": data.get("styling_rules", {}),
        "current_step": ["Stylist ✓"],
    }
