"""
File Generator Agent.

One instance runs per file, all in parallel via LangGraph's Send API.
Each instance receives the full plan as context so it can write correct
import paths even though it never sees the other files being generated.
"""

import json
from langchain_core.messages import SystemMessage
from app.agents.state import AgentState
from app.agents.utils import extract_json, retry_on_error
from app.core import memory as mem
from app.core.llm import get_llm
from app.core.logger import get_logger, Timer

log = get_logger(__name__)

FILE_GENERATOR_PROMPT = """\
You are a React + Tailwind expert. Generate ONE React/TypeScript file.

Respond ONLY with JSON (no markdown fences):
{"code": "<complete file contents>"}

RULES:
- Write the COMPLETE file — no placeholders, no TODOs.
- Tailwind CSS only (loaded via CDN — no CSS imports, no config files).
- No styled-jsx, no inline style objects.
- Every component MUST use `export default function X()` — NEVER named exports like `export const X = () =>`.
- Importing project files: ALWAYS use default import `import X from "./components/X"` — NEVER `import { X } from "./components/X"`.
- Use semantic HTML and accessible attributes (labels, aria, etc.).
- For form inputs: always pair <label> with htmlFor matching the input id.
- For file inputs (resume upload): use <input type="file"> with accept=".pdf,.doc,.docx".
- Import other project files using relative paths (e.g. import X from "./components/X").
- Make the UI polished: good spacing, hover states, focus rings, responsive layout.
- DO NOT use react-router-dom or any routing library — render all sections in one page using state or anchor links.
- ONLY import from: react, lucide-react, clsx, tailwind-merge, react-hook-form, framer-motion, date-fns, react-icons, @headlessui/react, recharts, or other files in this project.
- DO NOT use fetch() or any HTTP calls — use hardcoded/mock data only.
"""


@retry_on_error(retries=2)
async def file_generator_node(state: AgentState) -> dict:
    llm = get_llm(temperature=0, model_tier="large")

    current_file = state.get("current_file", {})
    file_path    = current_file.get("path", "App.tsx")
    description  = current_file.get("description", "")

    file_plan    = state.get("file_plan", [])
    plan_summary = "\n".join(
        f"  - {f['path']}: {f['description']}" for f in file_plan
    )

    existing_files = state.get("generated_files", {})
    existing_code  = existing_files.get(file_path, "")

    context_parts = [
        f"File to generate: {file_path}",
        f"Purpose: {description}",
        f"\nFull project file plan (for correct imports):\n{plan_summary}",
    ]
    if existing_code:
        context_parts.append(f"\nExisting code to modify:\n{existing_code}")
    if state.get("compilation_errors"):
        context_parts.append(f"\nErrors to fix:\n{chr(10).join(state['compilation_errors'])}")

    # Inject per-file error/fix history from session memory so the generator
    # doesn't repeat the same mistake it made in a previous turn.
    session_id = state.get("session_id", "")
    if session_id:
        file_history = mem.get_file_context(session_id, file_path)
        if file_history:
            context_parts.append(f"\n{file_history}")

    context = "\n".join(context_parts)

    log.info(f"Generating → {file_path} | \"{description[:60]}\"")
    t = Timer()

    system_messages = [
        SystemMessage(content=FILE_GENERATOR_PROMPT),
        SystemMessage(content=f"User request: {state['user_prompt']}"),
    ]
    # Inject project-level memory context (e.g. "this is a banking website, turn 2 fixed Header.tsx")
    memory_context = state.get("memory_context", "")
    if memory_context:
        system_messages.append(SystemMessage(content=memory_context))

    response = await llm.ainvoke([
        *system_messages,
        SystemMessage(content=context),
    ])

    data = extract_json(response.content)
    code = data.get("code", response.content.strip())

    log.info(f"Done in {t.elapsed()}s → {file_path} ({len(code)} chars)")

    return {
        "generated_file_parts": [{file_path: code}],
        "current_step":         [f"Generated {file_path} ✓"],
    }
