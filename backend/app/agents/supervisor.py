"""Supervisor Router Agent."""

import json
from langchain_core.messages import HumanMessage, SystemMessage
from app.agents.state import AgentState
from app.agents.utils import extract_json, retry_on_error
from app.core.llm import get_llm

SUPERVISOR_SYSTEM_PROMPT = """\
Route the user's request. Reply ONLY with JSON:
{"intent":"create"|"modify"|"fix","plan":"<one-line plan>","needs_architect":bool,"needs_stylist":bool,"needs_writer":bool}
Rules:
- "create": brand new project.
- "modify": adding features, changing content, or tweaking layout of EXISTING files.
- "fix": error repair (validator handles it).
"""


@retry_on_error(retries=2)
async def supervisor_node(state: AgentState) -> dict:
    llm = get_llm(temperature=0, model_tier="small")

    print(f"\n[Supervisor] Routing: {state['user_prompt'][:80]}...")
    response = await llm.ainvoke([
        SystemMessage(content=SUPERVISOR_SYSTEM_PROMPT),
        *state["messages"],
    ])
    print(f"[Supervisor] Plan: {response.content}")

    # Parse the response — we expect valid JSON
    data = extract_json(response.content)

    return {
        "messages": [response],
        "intent": data.get("intent", "create"),
        "plan": data.get("plan", ""),
        "needs_architect": data.get("needs_architect", True),
        "needs_stylist": data.get("needs_stylist", True),
        "needs_writer": data.get("needs_writer", True),
        "current_step": [f"Supervisor: {data.get('intent','create')} ✓"],
    }
