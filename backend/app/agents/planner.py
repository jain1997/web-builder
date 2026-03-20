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
from app.core.enums import Intent
from app.core.llm import get_llm
from app.core.logger import get_logger, Timer
from app.prompts import load_prompt

log = get_logger(__name__)

PLANNER_PROMPT = load_prompt("planner")


@retry_on_error(retries=2)
async def planner_node(state: AgentState) -> dict:
    llm = get_llm(temperature=0, model_tier="large")

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
    intent = data.get("intent", Intent.CREATE)
    files  = data.get("files", [])
    images = data.get("images", [])

    log.info(
        f"Done in {t.elapsed()}s | intent={intent} | "
        f"files={[f['path'] for f in files]} | images={[i['path'] for i in images]}"
    )

    return {
        "messages":     [response],
        "intent":       intent,
        "plan":         data.get("plan", ""),
        "file_plan":    files,
        "image_plan":   images,
        "current_step": [f"Planner: {intent} → {len(files)} file(s), {len(images)} image(s) ✓"],
    }
