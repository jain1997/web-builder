"""DOM Architect Agent."""

import json
from langchain_core.messages import SystemMessage
from app.agents.state import AgentState
from app.agents.utils import extract_json, retry_on_error
from app.core.llm import get_llm

ARCHITECT_SYSTEM_PROMPT = """\
You are a React expert. Generate React+Tailwind code based on the intent.
RULES:
- Main file: "App.tsx" (root level, NOT src/App.tsx).
- Components: "components/X.tsx" (NOT src/components/).
- Tailwind only (loaded via CDN, no config needed). No styled-jsx.
- Respond ONLY with JSON: {"component_schema":{...},"generated_files":{"App.tsx":"..."}}
- No markdown fences.

INTENT RULES:
- intent=create: Write a completely fresh App.tsx for the user's request. Ignore any existing file content — do NOT carry over starter/welcome screen content.
- intent=modify: Modify existing files to add/change the requested feature. Preserve unrelated existing content.
- intent=fix: Fix only the reported errors. Do not change other code.
"""


@retry_on_error(retries=2)
async def architect_node(state: AgentState) -> dict:
    llm = get_llm(temperature=0, model_tier="large")

    print(f"\n[Architect] Building/Modifying structure...")
    errors = state.get("compilation_errors", [])
    error_context = f"\n\nCURRENT ERRORS:\n{chr(10).join(errors)}" if errors else ""
    
    response = await llm.ainvoke([
        SystemMessage(content=ARCHITECT_SYSTEM_PROMPT),
        *state["messages"], # Context: what we've done so far
        SystemMessage(content=f"Intent: {state.get('intent', 'create')}\nPlan: {state.get('plan','')}\nExisting files:\n{json.dumps(state.get('generated_files', {}), indent=2)}{error_context}"),
    ])

    # Parse the response — we expect valid JSON
    data = extract_json(response.content)

    print(f"[Architect] Generated {len(data.get('generated_files', {}))} files.")
    return {
        "messages": [response],
        "component_schema": data.get("component_schema", {}),
        "generated_files": data.get("generated_files", {}),
        "current_step": ["Architect: structure ✓"],
    }
