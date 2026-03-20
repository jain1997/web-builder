"""QA / Validator Agent."""

import json
from langchain_core.messages import SystemMessage
from app.agents.state import AgentState
from app.agents.utils import extract_json, retry_on_error
from app.core.llm import get_llm
from app.core.logger import get_logger, Timer
from app.prompts import load_prompt

log = get_logger(__name__)

VALIDATOR_SYSTEM_PROMPT = load_prompt("validator")

MAX_RETRIES = 3


@retry_on_error(retries=2)
async def validator_node(state: AgentState) -> dict:
    errors = state.get("compilation_errors", [])
    retry_count = state.get("retry_count", 0)

    if not errors:
        log.info("Validator: no errors → approved ✓")
        return {"current_step": ["Validator: approved ✓"], "compilation_errors": []}

    if retry_count >= MAX_RETRIES:
        log.error(f"Validator: max retries ({MAX_RETRIES}) reached — shipping as-is")
        return {
            "current_step": [f"Validator: max retries reached, shipping as-is"],
            "compilation_errors": [],
        }

    llm = get_llm(temperature=0, model_tier="small")  # gpt-5-mini for exhaustive code fixing
    files = json.dumps(state.get("generated_files", {}), indent=2)
    errors_text = "\n".join(errors)

    log.warning(f"Fixing {len(errors)} error(s) — attempt {retry_count + 1}/{MAX_RETRIES}")
    t = Timer()
    response = await llm.ainvoke([
        SystemMessage(content=VALIDATOR_SYSTEM_PROMPT),
        SystemMessage(content=f"FILES:\n{files}\n\nERRORS:\n{errors_text}"),
    ])

    # Parse the response — we expect valid JSON
    try:
        data = extract_json(response.content)
    except Exception as e:
        log.error(f"Parse error on fix suggestion: {e}")
        return {"current_step": ["Validator: parse error"], "messages": [response]}

    log.info(f"Done in {t.elapsed()}s | summary: {data.get('fix_summary', 'approved')}")

    fixed_files = data.get("generated_files", {})

    if data.get("approved", False) or fixed_files:
        # Either explicitly approved, or files were returned (= fix was applied).
        # Either way, clear errors so route_validator sends to END.
        merged = {**state.get("generated_files", {}), **fixed_files}
        log.info(f"Validator: fixed {len(fixed_files)} file(s) → approved ✓")
        return {
            "messages": [response],
            "generated_files": merged,
            "current_step": [f"Validator: fixed {len(fixed_files)} file(s) ✓" if fixed_files else "Validator: approved ✓"],
            "compilation_errors": [],  # clear → route_validator → END
        }

    # No files returned and not approved — retry via planner
    log.warning(f"Validator: could not fix (attempt {retry_count + 1}/{MAX_RETRIES}), retrying via planner")
    return {
        "messages": [response],
        "compilation_errors": errors,  # keep → route_validator → planner retry
        "retry_count": retry_count + 1,
        "current_step": [f"Validator: retry {retry_count + 1}/{MAX_RETRIES}"],
    }
