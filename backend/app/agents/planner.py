"""
Planner Agent.

Fast, cheap node (small model) that determines:
  1. Intent (create / modify / fix)
  2. Exactly which files need to be created or modified
  3. A one-line description of each file's purpose
"""

import json
from langchain_core.messages import SystemMessage
from app.agents.state import AgentState
from app.agents.utils import extract_json, retry_on_error
from app.core.llm import get_llm
from app.core.logger import get_logger, Timer

log = get_logger(__name__)

PLANNER_PROMPT = """\
You are a React project planner. Given a user request, output a file plan — do NOT write any code.

Respond ONLY with JSON (no markdown):
{
  "intent": "create" | "modify" | "fix",
  "plan": "<one sentence summary>",
  "files": [
    {"path": "App.tsx", "description": "<what this file does and what it imports>"},
    {"path": "components/Foo.tsx", "description": "<what this component does>"}
  ]
}

RULES:
- intent=create  → list all files from scratch. App.tsx always first.
- intent=modify  → list ONLY the files that need changes.
- intent=fix     → return "files": [] ONLY when no specific file can be identified from the error.
- File paths: root-level App.tsx, components in components/ (no src/ prefix).
- Keep it lean: 1 file for trivial UIs, 2-4 for moderate, max 6 for complex apps.
- Each description MUST mention what the file imports from other files in the plan,
  so generators can write correct import paths without seeing each other's code.
- Tailwind CSS is loaded via CDN — no config files needed.

WHEN COMPILATION/RENDERING ERRORS ARE PRESENT — follow these rules strictly:
- DO NOT use intent=fix with empty files — the validator alone cannot fix most runtime errors.
- Instead, identify which files are broken and use intent=modify to REGENERATE them cleanly.
- Regenerating with the error as context is far more reliable than surgical patching.

Error patterns → files to regenerate:
- "Element type is invalid…undefined…render method of `X`"
    → X has a wrong/missing export, OR its parent imports it incorrectly.
    → Regenerate: the file that defines X (e.g. components/X.tsx) AND App.tsx (or whatever imports X).
- "Cannot find module './components/X'" or "Module not found: components/X"
    → components/X.tsx is missing or has the wrong path.
    → Regenerate: components/X.tsx and the file that imports it.
- "SyntaxError in /components/X.tsx line N" or "Unexpected token in X.tsx"
    → Regenerate: only components/X.tsx.
- "Objects are not valid as React children" in component X
    → Regenerate: the file rendering those objects.
- "X is not a function" / "X is not a constructor"
    → Regenerate: the file that defines X and the file that calls it.
- Fallback: if the error gives no file hint at all → use intent=fix (files=[]).
"""


@retry_on_error(retries=2)
async def planner_node(state: AgentState) -> dict:
    llm = get_llm(temperature=0, model_tier="small")

    existing = state.get("generated_files", {})
    errors   = state.get("compilation_errors", [])

    context_parts = []
    if existing:
        summary = {p: code.splitlines()[0] for p, code in existing.items()}
        context_parts.append(f"Existing files (paths + first line):\n{json.dumps(summary, indent=2)}")
    if errors:
        context_parts.append(f"Errors:\n{chr(10).join(errors)}")
    context = "\n\n".join(context_parts)

    log.info(f"Planning → prompt: \"{state['user_prompt'][:80]}...\"")
    t = Timer()

    memory_context = state.get("memory_context", "")

    system_messages = [SystemMessage(content=PLANNER_PROMPT)]
    if memory_context:
        system_messages.append(SystemMessage(content=memory_context))

    response = await llm.ainvoke([
        *system_messages,
        *state["messages"],
        *([SystemMessage(content=context)] if context else []),
    ])

    data   = extract_json(response.content)
    intent = data.get("intent", "create")
    files  = data.get("files", [])

    log.info(f"Done in {t.elapsed()}s | intent={intent} | files={[f['path'] for f in files]}")

    return {
        "messages":     [response],
        "intent":       intent,
        "plan":         data.get("plan", ""),
        "file_plan":    files,
        "current_step": [f"Planner: {intent} → {len(files)} file(s) ✓"],
    }
