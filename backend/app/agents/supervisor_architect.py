"""
Combined Supervisor + Architect Agent.

Replaces the two sequential LLM calls (supervisor → architect) with a single
gpt-4o call that simultaneously routes the request AND generates the code.
Saves one full round-trip of latency on every user prompt.
"""

import json
from langchain_core.messages import SystemMessage
from app.agents.state import AgentState
from app.agents.utils import extract_json, retry_on_error
from app.core.llm import get_llm

SUPERVISOR_ARCHITECT_PROMPT = """\
You are a React expert and task router. For each user request, do TWO things in ONE response:
  1. Route the request (intent, flags)
  2. Generate the React code (unless intent is "fix")

RESPOND ONLY with JSON — no markdown fences:
{
  "intent": "create" | "modify" | "fix",
  "plan": "<one-line description of what you're building>",
  "needs_stylist": false,
  "needs_writer": false,
  "component_schema": {},
  "generated_files": {"App.tsx": "..."}
}

━━━ INTENT RULES ━━━
- "create"  → Brand new UI from scratch. Ignore any existing starter/welcome content.
- "modify"  → Add or change a specific feature. Preserve everything else in existing files.
- "fix"     → Bug/error repair. Return empty generated_files — the validator handles it.

━━━ FILE RULES ━━━
- Main entry: "App.tsx"  (root level — NOT src/App.tsx, NOT app/page.tsx)
- Components: "components/ComponentName.tsx"  (NOT src/components/)
- Tailwind CSS only — it is loaded via CDN, no config files needed
- No CSS imports, no styled-jsx, no inline style objects
- Import components with relative paths: import X from "./components/X"

━━━ CODE QUALITY ━━━
- Write complete, production-quality code — not placeholders
- Every component must be a valid default export
- Use semantic HTML and accessible attributes
- Make the UI look polished: proper spacing, colors, hover states

━━━ ROUTING FLAGS ━━━
- needs_stylist: true ONLY if styling is intentionally left rough for stylist to enhance
- needs_writer:  true ONLY if text content needs a separate writing pass
- For almost all requests: set BOTH to false — generate complete code directly
- For "fix" intent: BOTH must be false, generated_files must be {}
"""


@retry_on_error(retries=2)
async def supervisor_architect_node(state: AgentState) -> dict:
    llm = get_llm(temperature=0, model_tier="large")

    existing = state.get("generated_files", {})
    errors = state.get("compilation_errors", [])

    context_parts = []
    if existing:
        context_parts.append(f"Existing files:\n{json.dumps(existing, indent=2)}")
    if errors:
        context_parts.append(f"Compilation errors:\n{chr(10).join(errors)}")
    context = "\n\n".join(context_parts)

    print(f"\n[SupervisorArchitect] Routing + generating for: {state['user_prompt'][:80]}...")

    response = await llm.ainvoke([
        SystemMessage(content=SUPERVISOR_ARCHITECT_PROMPT),
        *state["messages"],
        *(  [SystemMessage(content=context)] if context else [] ),
    ])

    data = extract_json(response.content)

    intent = data.get("intent", "create")
    generated = data.get("generated_files", {})

    print(f"[SupervisorArchitect] intent={intent}, files={list(generated.keys())}, "
          f"needs_stylist={data.get('needs_stylist')}, needs_writer={data.get('needs_writer')}")

    return {
        "messages": [response],
        "intent": intent,
        "plan": data.get("plan", ""),
        "needs_architect": False,
        "needs_stylist": data.get("needs_stylist", False),
        "needs_writer": data.get("needs_writer", False),
        "component_schema": data.get("component_schema", {}),
        "generated_files": generated,
        "current_step": [f"SupervisorArchitect: {intent} ✓"],
    }
