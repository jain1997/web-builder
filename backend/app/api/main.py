"""
FastAPI application — the Agentic Brain API.

Provides:
  - GET  /health              → dependency health check
  - GET  /v1/template         → starter template files
  - GET  /v1/images/:sid/:fn  → generated images
  - POST /v1/generate         → SSE streaming agent pipeline
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from pathlib import Path
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from langchain_core.messages import HumanMessage, AIMessage
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from contextlib import asynccontextmanager

from app.agents.graph import agent_graph
from app.agents.state import AgentState
from app.core import memory as mem
from app.core import database as db
from app.core import redis_client as rc
from app.core.config import settings
from app.core.enums import Intent
from app.core.logger import get_logger, Timer, set_correlation_id
from app.templates.starter import STARTER_FILES

log = get_logger(__name__)


# ───────────────────────────────────────────────────────────────────
# Active pipeline tracking for graceful shutdown
# ───────────────────────────────────────────────────────────────────
_active_pipelines: set[asyncio.Task] = set()
SHUTDOWN_DRAIN_TIMEOUT = 30

MAX_PROMPT_LENGTH = 5000
RATE_LIMIT_WINDOW = 60
RATE_LIMIT_MAX = 10

_rate_limits: dict[str, list[float]] = {}


def _check_rate_limit(session_id: str) -> bool:
    now = time.time()
    window_start = now - RATE_LIMIT_WINDOW
    timestamps = _rate_limits.get(session_id, [])
    timestamps = [t for t in timestamps if t > window_start]
    timestamps.append(now)
    _rate_limits[session_id] = timestamps
    return len(timestamps) <= RATE_LIMIT_MAX


# ───────────────────────────────────────────────────────────────────
# Auth dependency
# ───────────────────────────────────────────────────────────────────
async def verify_auth(request: Request) -> None:
    """If WS_AUTH_KEY is configured, require Bearer token on protected routes."""
    if not settings.WS_AUTH_KEY:
        return
    auth = request.headers.get("Authorization", "")
    if auth != f"Bearer {settings.WS_AUTH_KEY}":
        raise HTTPException(status_code=401, detail="Unauthorized")


# ───────────────────────────────────────────────────────────────────
# Lifecycle
# ───────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init_db()
    log.info("Database initialized")
    yield
    if _active_pipelines:
        log.info(f"Shutting down — waiting for {len(_active_pipelines)} active pipeline(s)…")
        done, pending = await asyncio.wait(_active_pipelines, timeout=SHUTDOWN_DRAIN_TIMEOUT)
        if pending:
            log.warning(f"{len(pending)} pipeline(s) did not finish — cancelling")
            for task in pending:
                task.cancel()
    await db.close_db()
    await rc.close_redis()
    log.info("Connections closed")


# ───────────────────────────────────────────────────────────────────
# App
# ───────────────────────────────────────────────────────────────────
app = FastAPI(title="Agentic Web IDE — Backend", version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


# ───────────────────────────────────────────────────────────────────
# Health
# ───────────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    checks: dict[str, str] = {}

    try:
        r = await rc.get_redis()
        await r.ping()
        checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = f"error: {e}"

    try:
        if Path(settings.DATABASE_PATH).exists():
            checks["sqlite"] = "ok"
        else:
            checks["sqlite"] = "warning: db not created yet"
    except Exception as e:
        checks["sqlite"] = f"error: {e}"

    checks["openai_key"] = "ok" if settings.OPENAI_API_KEY else "missing"

    healthy = all(v == "ok" for v in checks.values())
    return {"status": "ok" if healthy else "degraded", "version": "0.2.0", "checks": checks}


# ───────────────────────────────────────────────────────────────────
# Versioned API router
# ───────────────────────────────────────────────────────────────────
v1 = APIRouter(prefix="/v1")


@v1.get("/template")
async def get_template():
    return {"files": STARTER_FILES}


@v1.get("/images/{session_id}/{filename}")
async def serve_image(session_id: str, filename: str):
    safe_name = Path(filename).name
    image_path = Path(settings.IMAGE_STORAGE_PATH) / session_id / safe_name
    if not image_path.exists():
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(image_path, media_type="image/png")


# ───────────────────────────────────────────────────────────────────
# SSE Generate — the main pipeline endpoint
# ───────────────────────────────────────────────────────────────────

class GenerateRequest(BaseModel):
    prompt: str = Field(..., max_length=MAX_PROMPT_LENGTH)
    session_id: str = Field(default="default")
    files: dict[str, str] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    history: list[dict[str, str]] = Field(default_factory=list)


def _sse_event(event: str, data: dict) -> dict:
    """Format an SSE event payload."""
    return {"event": event, "data": json.dumps(data)}


async def _pipeline_stream(body: GenerateRequest) -> AsyncGenerator[dict, None]:
    """
    Run the agent pipeline and yield SSE events.

    Events:
      event: status   → {"step": "...", "node": "...", "files": {...}}
      event: result   → {"files": {...}, "session_id": "...", "step": "..."}
      event: error    → {"message": "..."}
      event: heartbeat → {} (keep-alive every 15s, ignored by client)
    """
    session_id = body.session_id
    user_prompt = body.prompt
    current_files = body.files
    compilation_errors = body.errors

    set_correlation_id(session_id)
    log.info(f"Pipeline start → \"{user_prompt[:80]}…\"")

    await mem.start_session(session_id)
    memory_context = await mem.get_planner_context(session_id)

    yield _sse_event("status", {"step": "Received prompt — starting agent pipeline…", "node": "system"})

    # Reconstruct LangChain message history
    messages: list = []
    for m in body.history:
        if m.get("role") == "user":
            messages.append(HumanMessage(content=m["content"]))
        elif m.get("role") == "assistant":
            messages.append(AIMessage(content=m["content"]))

    if not messages or messages[-1].content != user_prompt:
        messages.append(HumanMessage(content=user_prompt))

    # Detect fresh project
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
        "session_id":         session_id,
        "memory_context":     memory_context,
        "user_prompt":        user_prompt,
        "messages":           messages,
        "component_schema":   {},
        "generated_files":    {} if is_fresh_project else current_files,
        "styling_rules":      {},
        "compilation_errors": compilation_errors,
        "retry_count":        0,
        "current_step":       ["Starting agent pipeline…"],
    }

    final_state = dict(initial_state)
    pipeline_timer = Timer()
    current_task = asyncio.current_task()
    if current_task:
        _active_pipelines.add(current_task)

    try:
        async for event in agent_graph.astream(initial_state, stream_mode="updates"):
            for node_name, node_output in event.items():
                final_state.update(node_output)

                raw_step = node_output.get("current_step", [])
                step = " | ".join(raw_step) if isinstance(raw_step, list) else str(raw_step)
                node_files = node_output.get("generated_files")

                log.info(f"[{node_name}] {step}")
                yield _sse_event("status", {
                    "step": step,
                    "node": node_name,
                    "files": node_files,
                })

        # Persist turn
        generated = final_state.get("generated_files", {})
        await mem.save_turn(
            session_id,
            prompt=user_prompt,
            intent=final_state.get("intent", Intent.CREATE),
            plan=final_state.get("plan", ""),
            files_touched=list(generated.keys()),
            errors=compilation_errors,
            fix_summary=" | ".join(
                s for s in final_state.get("current_step", [])
                if "fixed" in s.lower() or "validator" in s.lower()
            ),
            generated_files=generated,
        )

        yield _sse_event("result", {
            "files": generated,
            "schema": final_state.get("component_schema", {}),
            "step": "Generation complete ✓",
            "session_id": session_id,
        })
        log.info(f"Pipeline finished in {pipeline_timer.elapsed()}s ✓")

    except asyncio.CancelledError:
        log.warning("Pipeline cancelled (client disconnected)")
        yield _sse_event("error", {"message": "Pipeline cancelled"})

    except Exception as e:
        log.exception(f"Pipeline error: {e}")
        yield _sse_event("error", {"message": f"Agent pipeline error: {str(e)}"})

    finally:
        if current_task:
            _active_pipelines.discard(current_task)


@v1.post("/generate", dependencies=[Depends(verify_auth)])
async def generate(body: GenerateRequest):
    """
    Start the agent pipeline and stream results via SSE.

    Returns a text/event-stream response. Each event has:
      event: status | result | error
      data: JSON payload
    """
    if not _check_rate_limit(body.session_id):
        raise HTTPException(
            status_code=429,
            detail=f"Rate limited — max {RATE_LIMIT_MAX} requests per {RATE_LIMIT_WINDOW}s.",
        )

    return EventSourceResponse(
        _pipeline_stream(body),
        media_type="text/event-stream",
        ping=15,  # keep-alive ping every 15 seconds
    )


app.include_router(v1)

# Backward-compatible aliases
app.get("/api/template")(get_template)
app.get("/api/images/{session_id}/{filename}")(serve_image)
