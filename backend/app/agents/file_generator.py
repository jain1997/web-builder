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
from app.prompts import load_prompt

log = get_logger(__name__)

FILE_GENERATOR_PROMPT = load_prompt("file_generator")


@retry_on_error(retries=2)
async def file_generator_node(state: AgentState) -> dict:
    llm = get_llm(temperature=0, model_tier="small")

    current_file = state.get("current_file", {})
    file_path    = current_file.get("path", "App.tsx")
    description  = current_file.get("description", "")

    file_plan    = state.get("file_plan", [])
    plan_summary = "\n".join(
        f"  - {f['path']}: {f['description']}" for f in file_plan
    )

    existing_files = state.get("generated_files", {})
    existing_code  = existing_files.get(file_path, "")

    # Build image availability summary so generated code uses correct paths
    image_plan = state.get("image_plan", [])
    image_summary = ""
    if image_plan:
        image_lines = "\n".join(
            f"  - /{img['path']}: {img.get('prompt', '')[:80]}" for img in image_plan
        )
        image_summary = (
            f"\nAvailable images (use these exact paths as src in <img> tags):\n"
            f"{image_lines}"
        )

    context_parts = [
        f"File to generate: {file_path}",
        f"Purpose: {description}",
        f"\nFull project file plan (for correct imports):\n{plan_summary}",
    ]
    if image_summary:
        context_parts.append(image_summary)
    if existing_code:
        context_parts.append(f"\nExisting code to modify:\n{existing_code}")
    if state.get("compilation_errors"):
        context_parts.append(f"\nErrors to fix:\n{chr(10).join(state['compilation_errors'])}")

    # Inject per-file error/fix history and previous code snapshot from SQLite
    # so the generator doesn't repeat past mistakes and can make targeted edits.
    session_id = state.get("session_id", "")
    if session_id:
        file_history = await mem.get_file_context(session_id, file_path)
        if file_history:
            context_parts.append(f"\n{file_history}")

        # If no existing code was passed in state, check SQLite for the last snapshot
        if not existing_code:
            previous_code = await mem.get_previous_file(session_id, file_path)
            if previous_code:
                context_parts.append(
                    f"\nPrevious version of this file (from last turn — "
                    f"make targeted edits, don't rewrite from scratch):\n{previous_code}"
                )

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
