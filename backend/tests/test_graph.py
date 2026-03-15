import asyncio
import os
import json
from app.agents.graph import agent_graph
from langchain_core.messages import HumanMessage

async def test_graph():
    print("Testing LangGraph Pipeline...")
    
    # Mock state
    initial_state = {
        "user_prompt": "Create an ultra-premium landing page for a space travel agency called 'Galactic Voyages'.",
        "messages": [HumanMessage(content="Create an ultra-premium landing page for a space travel agency called 'Galactic Voyages'.")],
        "component_schema": {},
        "generated_files": {},
        "styling_rules": {},
        "compilation_errors": [],
        "retry_count": 0,
        "current_step": "",
    }

    try:
        async for event in agent_graph.astream(
            initial_state,
            stream_mode="updates",
        ):
            for node_name, node_output in event.items():
                print(f"\n[Node: {node_name}]")
                step = node_output.get("current_step", "Completed")
                print(f"  Step: {step}")
        
        final_state = await agent_graph.ainvoke(initial_state)
        print("\n[Final Result]")
        print(f"  Generated Files: {list(final_state['generated_files'].keys())}")
        print(f"  Component Schema Keys: {list(final_state['component_schema'].keys())}")
        
        if "app/page.tsx" in final_state['generated_files']:
            print("  app/page.tsx generated successfully.")
        
    except Exception as e:
        print(f"Error during graph execution: {e}")

if __name__ == "__main__":
    # Check for API Key
    if not os.getenv("OPENAI_API_KEY"):
        print("WARNING: OPENAI_API_KEY not set. Graph execution will fail.")
    else:
        asyncio.run(test_graph())
