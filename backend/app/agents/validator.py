"""QA / Validator Agent."""

import json
from langchain_core.messages import SystemMessage
from app.agents.state import AgentState
from app.agents.utils import extract_json, retry_on_error
from app.core.llm import get_llm
from app.core.logger import get_logger, Timer

log = get_logger(__name__)

VALIDATOR_SYSTEM_PROMPT = """\
You are a React + Tailwind expert. Your job is to fix broken React code given error messages.

Respond ONLY with JSON:
{"approved": bool, "generated_files": {"path": "full fixed code", ...}, "fix_summary": "..."}

RULES:
- Inspect ALL files provided and the errors carefully before deciding what to change.
- Files use "App.tsx" (root level) and "components/X.tsx" — never src/ paths.
- Tailwind CSS only (loaded via CDN). No CSS imports, no styled-jsx.
- Return the COMPLETE fixed file contents — not a diff, not a snippet.
- Set "approved": true when the fix is applied (even if you changed files).
- Set "approved": false only if the error is completely unfixable.

EXPORT/IMPORT RULES (always apply when fixing any file):
- Every component MUST use `export default function X()` — NEVER `export const X = () =>` or `export function X()` without default.
- Every cross-file import MUST use default import style: `import X from "./components/X"` — NEVER `import { X } from "./components/X"`.
- If you change exports in one file, also fix imports of that file in all other files you return.

COMMON REACT ERROR FIXES:
- "Element type is invalid…undefined…render method of `X`":
    X is imported as undefined because of an export/import mismatch.
    Fix: ensure components/X.tsx has `export default function X()` AND
    every importer uses `import X from "./components/X"` (no braces).
    Return BOTH the component file AND every file that imports it.
- "Cannot find module './X'" or missing module:
    The import path is wrong. Check and correct the path in the importer.
- "Objects are not valid as React children":
    A JS object is being rendered directly. Wrap with JSON.stringify() or extract a string field.
- "X is not a function":
    X is imported as default but exported as named, or vice versa. Fix the import/export.
- Syntax errors: find the reported line and fix the syntax.
"""

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

    llm = get_llm(temperature=0, model_tier="large")  # use gpt-4o — runtime errors need full reasoning
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
