"""Content Writer Agent."""

import json
from langchain_core.messages import SystemMessage
from app.agents.state import AgentState
from app.agents.utils import extract_json, retry_on_error
from app.core.llm import get_llm

WRITER_SYSTEM_PROMPT = """\
You are a UX copywriter. Improve the text content in the given React files.
RULES:
- ONLY change text strings, labels, placeholder text, and copy — NOT className or structure.
- Do NOT delete existing components, props, or logic.
- Respond ONLY with JSON: {"generated_files":{...}}
- No markdown fences.
"""

# Writer only needs renderable files with user-visible text
_WRITER_EXTENSIONS = (".tsx", ".jsx", ".html")


@retry_on_error(retries=2)
async def writer_node(state: AgentState) -> dict:
    llm = get_llm(temperature=0.4, model_tier="small")

    # Only send files that contain user-visible text
    all_files = state.get("generated_files", {})
    relevant  = {p: c for p, c in all_files.items() if p.endswith(_WRITER_EXTENSIONS)}
    files_str = json.dumps(relevant or all_files, indent=2)

    prompt    = state["user_prompt"]
    errors    = state.get("compilation_errors", [])
    error_ctx = f"\n\nCURRENT ERRORS:\n{chr(10).join(errors)}" if errors else ""

    print(f"\n[Writer] Polishing copy in {len(relevant)} file(s)...")

    # No full message history — writer only needs the prompt + current files
    response = await llm.ainvoke([
        SystemMessage(content=WRITER_SYSTEM_PROMPT),
        SystemMessage(content=f"User request: {prompt}\n\nFiles to improve:\n{files_str}{error_ctx}"),
    ])

    print("[Writer] Done.")
    data = extract_json(response.content)

    return {
        "writer_files": data.get("generated_files", {}),
        "current_step": ["Writer ✓"],
    }
