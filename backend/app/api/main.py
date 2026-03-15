"""
FastAPI application — the Agentic Brain API.

Provides:
  - GET  /health       → health check
  - GET  /api/template → starter template files
  - WS   /ws/chat      → real-time agent pipeline communication
"""

from __future__ import annotations

import asyncio
import json
import uuid

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from langchain_core.messages import HumanMessage, AIMessage

from app.agents.graph import agent_graph
from app.agents.state import AgentState
from app.core import memory as mem
from app.core.config import settings
from app.core.logger import get_logger, Timer
from app.templates.starter import STARTER_FILES

log = get_logger(__name__)

# ───────────────────────────────────────────────────────────────────
# App
# ───────────────────────────────────────────────────────────────────
app = FastAPI(title="Agentic Web IDE — Backend", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ───────────────────────────────────────────────────────────────────
# Helpers
# ───────────────────────────────────────────────────────────────────
async def safe_send(ws: WebSocket, payload: dict) -> bool:
    """Send JSON to client. Returns False if the connection is gone."""
    try:
        await ws.send_json(payload)
        return True
    except (WebSocketDisconnect, RuntimeError):
        return False


async def heartbeat(ws: WebSocket, stop_event: asyncio.Event, interval: float = 5.0):
    """
    Send a lightweight 'thinking' ping every `interval` seconds while the
    LLM is generating. Keeps the browser WebSocket from timing out on long
    generations (e.g. complex forms, multi-file apps).
    """
    while not stop_event.is_set():
        await asyncio.sleep(interval)
        if stop_event.is_set():
            break
        ok = await safe_send(ws, {"type": "status", "step": "Thinking…", "node": "llm"})
        if not ok:
            break


# ───────────────────────────────────────────────────────────────────
# Health
# ───────────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}


# ───────────────────────────────────────────────────────────────────
# Starter template
# ───────────────────────────────────────────────────────────────────
@app.get("/api/template")
async def get_template():
    return {"files": STARTER_FILES}


# ───────────────────────────────────────────────────────────────────
# WebSocket — real-time agent pipeline
# ───────────────────────────────────────────────────────────────────
@app.websocket("/ws/chat")
async def websocket_chat(ws: WebSocket):
    await ws.accept()

    try:
        while True:
            raw = await ws.receive_text()
            data = json.loads(raw)

            user_prompt        = data.get("prompt", "")
            current_files      = data.get("files", {})
            compilation_errors = data.get("errors", [])
            history_data       = data.get("history", [])
            session_id         = data.get("session_id", "default")

            if not user_prompt:
                await safe_send(ws, {"type": "error", "message": "Empty prompt"})
                continue

            log.info(f"Pipeline start [session={session_id[:8]}] → \"{user_prompt[:80]}…\"")
            memory_context = mem.get_planner_context(session_id)

            await safe_send(ws, {
                "type": "status",
                "step": "Received prompt — starting agent pipeline…",
            })

            # Reconstruct message history
            messages: list = []
            for m in history_data:
                if m["role"] == "user":
                    messages.append(HumanMessage(content=m["content"]))
                elif m["role"] == "assistant":
                    messages.append(AIMessage(content=m["content"]))

            if not messages or messages[-1].content != user_prompt:
                messages.append(HumanMessage(content=user_prompt))

            # Detect fresh project or explicit "start over / just X" requests
            _simplify_keywords = [
                "i just want", "just want", "just show", "only show", "only a ",
                "just a ", "start over", "start fresh", "scratch that", "from scratch",
            ]
            user_wants_fresh = any(kw in user_prompt.lower() for kw in _simplify_keywords)
            is_fresh_project = (
                set(current_files.keys()) <= {"App.tsx", "public/index.html"}
                or user_wants_fresh
            )
            if is_fresh_project:
                session_id = str(uuid.uuid4())
                log.info(f"Fresh project detected — new session_id={session_id[:8]}")

            initial_state: AgentState = {
                "session_id":      session_id,
                "memory_context":  memory_context,
                "user_prompt":     user_prompt,
                "messages":        messages,
                "component_schema": {},
                "generated_files": {} if is_fresh_project else current_files,
                "styling_rules":   {},
                "compilation_errors": compilation_errors,
                "retry_count":     0,
                "current_step":    ["Starting agent pipeline…"],
            }

            final_state = dict(initial_state)
            pipeline_timer = Timer()

            # ── Start heartbeat to keep WS alive during long LLM calls ──
            stop_heartbeat = asyncio.Event()
            hb_task = asyncio.create_task(heartbeat(ws, stop_heartbeat))

            try:
                async for event in agent_graph.astream(
                    initial_state,
                    stream_mode="updates",
                ):
                    for node_name, node_output in event.items():
                        final_state.update(node_output)

                        raw_step = node_output.get("current_step", [])
                        step = " | ".join(raw_step) if isinstance(raw_step, list) else str(raw_step)

                        node_files = node_output.get("generated_files")

                        log.info(f"[{node_name}] {step}")
                        ok = await safe_send(ws, {
                            "type": "status",
                            "step": step,
                            "node": node_name,
                            "files": node_files,
                        })
                        if not ok:
                            log.warning("Client disconnected mid-stream — aborting pipeline")
                            break
                    else:
                        continue
                    break  # inner break propagates out of the async for

                # ── Persist turn to session memory ──────────────────
                generated = final_state.get("generated_files", {})
                mem.save_turn(
                    session_id,
                    prompt      = user_prompt,
                    intent      = final_state.get("intent", "create"),
                    plan        = final_state.get("plan", ""),
                    files_touched = list(generated.keys()),
                    errors      = compilation_errors,
                    fix_summary = " | ".join(
                        s for s in final_state.get("current_step", [])
                        if "fixed" in s.lower() or "validator" in s.lower()
                    ),
                )

                # Send final result (only if still connected)
                await safe_send(ws, {
                    "type": "result",
                    "files": generated,
                    "schema": final_state.get("component_schema", {}),
                    "step": "Generation complete ✓",
                    "session_id": session_id,
                })
                log.info(f"Pipeline finished in {pipeline_timer.elapsed()}s ✓")

            except Exception as e:
                log.exception(f"Pipeline error: {e}")
                await safe_send(ws, {
                    "type": "error",
                    "message": f"Agent pipeline error: {str(e)}",
                })
            finally:
                # Always stop the heartbeat when pipeline finishes or errors
                stop_heartbeat.set()
                hb_task.cancel()

    except WebSocketDisconnect:
        pass
    except Exception as e:
        log.exception(f"Unhandled WebSocket error: {e}")
