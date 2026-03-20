<div align="center">

# Agentic Web IDE

**AI-powered browser IDE that turns plain English into live React applications.**

Describe a UI in natural language — watch AI agents generate multi-file React + Tailwind code,
rendered instantly in a Sandpack preview. No setup, no build tools, no deployments.

[![CI](https://github.com/your-username/agentic-ui/actions/workflows/ci.yml/badge.svg)](https://github.com/your-username/agentic-ui/actions)
[![Python 3.13](https://img.shields.io/badge/python-3.13-blue.svg)](https://www.python.org/)
[![Next.js](https://img.shields.io/badge/Next.js-15-black.svg)](https://nextjs.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

</div>

---

## Quick Start

```bash
# 1. Clone and configure
git clone https://github.com/your-username/agentic-ui.git
cd agentic-ui
cp backend/.env.example backend/.env
# Set your OPENAI_API_KEY in backend/.env

# 2. Deploy (pick one)
./deploy.sh              # Docker Compose (recommended)
./deploy.sh local        # Local dev without Docker
```

Open **http://localhost:3000** and start prompting.

---

## How It Works

```
User types prompt
      |
      v
  POST /v1/generate (SSE stream)
      |
      v
+---------------------------------------------------------------+
|                    LangGraph Pipeline                          |
|                                                               |
|   planner -----> Send fan-out -----> file_generator x N       |
|   (gpt-5-mini)       |               (gpt-5.1, parallel)     |
|                      |                       |                |
|                      +--- image_generator ---+                |
|                      | (OpenAI/Ollama)       |                |
|                      +-----------------------+                |
|                              v                                |
|                          assembler                            |
|                              v                                |
|                          validator -----> retry (max 3)       |
|                              |                                |
|                             END                               |
+---------------------------------------------------------------+
      |
      v
  SSE event stream (status + files)
      |
      v
  Sandpack (react-ts, browser bundler)
  Live preview updates in real-time
```

---

## Architecture

### System Overview

```
+-------------------+     SSE      +-------------------+     Cache     +-------+
|                   | <----------> |                   | <-----------> | Redis |
|   Next.js 15      |   POST       |   FastAPI         |               +-------+
|   (React + TS)    |   /v1/gen    |   (Uvicorn)       |
|                   |              |                   |     Store     +--------+
|   - Sandpack      |              |   - LangGraph     | <----------> | SQLite |
|   - Zustand       |              |   - OpenAI        |               +--------+
|   - Tailwind      |              |   - Ollama        |
+-------------------+              +-------------------+     Images   +--------+
     :3000                              :8000           <----------> | Disk   |
                                                                      +--------+
```

### Backend — Python / FastAPI

#### Agent Pipeline (`backend/app/agents/`)

| File | Role | Model |
|---|---|---|
| `planner.py` | Decides intent (`create` / `modify` / `fix`) and produces a file plan with paths and descriptions. | GPT-5-mini |
| `file_generator.py` | One instance per file, all run **in parallel** via LangGraph `Send` API. Generates complete React/TypeScript files with conversation-aware context. | GPT-5.1 |
| `image_generator.py` | Generates images via Ollama (Flux2) and stores them on disk. Returns HTTP URLs for use in generated code. | Flux2 (local) |
| `validator.py` | Receives compilation errors from the frontend, makes surgical fixes. Retries up to 3 times. | GPT-5-mini |
| `graph.py` | Wires the LangGraph state graph: `planner -> Send fan-out -> assembler -> validator`. | -- |
| `state.py` | `AgentState` TypedDict — single source of truth flowing through the graph. Uses `operator.add` for parallel accumulation. | -- |
| `utils.py` | `extract_json()` (robust JSON extractor) and `@retry_on_error` decorator. | -- |

#### Core (`backend/app/core/`)

| File | Purpose |
|---|---|
| `config.py` | Pydantic `BaseSettings` with validation — fails fast on missing `OPENAI_API_KEY`. |
| `llm.py` | Singleton LLM cache. One `ChatOpenAI` instance per `(provider, tier, temperature, streaming)` tuple. |
| `redis_client.py` | Redis async client with graceful degradation — falls back to SQLite on connection failure. |
| `database.py` | SQLite (WAL mode) with connection pooling. Stores conversation history, file snapshots, and error context. |
| `memory.py` | Async facade unifying Redis (cache) + SQLite (persistence) for session state. |
| `logger.py` | Dual-mode logging: colored dev output or structured JSON. Correlation IDs via `contextvars`. |
| `enums.py` | `StrEnum` types (`Intent`, `WSMessageType`, `ModelTier`) eliminating magic strings. |

#### API Endpoints (`backend/app/api/main.py`)

| Method | Path | Description |
|---|---|---|
| `POST` | `/v1/generate` | SSE streaming endpoint — runs the agent pipeline and streams status/result events. |
| `GET` | `/v1/template` | Returns starter `App.tsx` template for IDE initialization. |
| `GET` | `/v1/images/{session}/{file}` | Serves generated images from disk. |
| `GET` | `/health` | Health check with Redis and SQLite dependency status. |

#### Prompt Templates (`backend/app/prompts/`)

System prompts are stored as `.md` files loaded via `load_prompt()` with `@lru_cache`. Separates prompt engineering from application code.

### Frontend — Next.js 15 / TypeScript

#### Components (`frontend/src/components/`)

| File | Purpose |
|---|---|
| `LivePreview.tsx` | Sandpack `react-ts` template with browser bundler. Tailwind injected via CDN. Remounts on file set changes. |
| `ChatPanel.tsx` | Chat UI with message history, agent step visualization, and cancel support. |
| `CodeEditor.tsx` | Syntax-highlighted code viewer with file tab switching and diff view. |
| `ErrorBoundary.tsx` | React error boundary — catches per-panel render failures with retry. |

#### State & Hooks

| File | Purpose |
|---|---|
| `lib/store.ts` | Zustand store with `localStorage` persistence. Saves files, messages (last 50), and active file across refreshes. |
| `hooks/useChat.ts` | SSE streaming via `fetch()` + `ReadableStream`. Parses server events, dispatches to store, supports `AbortController` cancellation. |

---

## Key Features

### SSE Streaming

The backend uses **Server-Sent Events** instead of WebSocket for real-time communication:

- Works through CDNs, proxies, and load balancers without special configuration
- Standard HTTP — supports Bearer token auth, rate limiting, and CORS out of the box
- 15-second keep-alive pings prevent connection timeouts
- Frontend cancellation via `AbortController`

### Parallel File Generation

When the planner outputs a multi-file plan, LangGraph's `Send` API dispatches one `file_generator` node per file — all running **simultaneously**:

```python
return [
    Send("file_generator", {**state, "current_file": file_info})
    for file_info in file_plan
]
```

Generation time for N files ~ generation time for 1 file.

### Dual Storage: Redis + SQLite

| Layer | Store | Purpose |
|---|---|---|
| Hot cache | Redis | Active session state, file snapshots (TTL-based) |
| Persistence | SQLite | Conversation history, error context, file snapshots |

Redis is **optional** — the app gracefully degrades to SQLite-only mode when Redis is unavailable.

### Auto-Fix Loop

The frontend detects Sandpack compilation errors and automatically sends them back to the backend for repair. A guard ensures only one fix attempt per generation cycle to prevent infinite loops.

### Image Generation

Two providers supported — configured via `IMAGE_PROVIDER` in `.env`:

| Provider | Model | Speed | Cost |
|---|---|---|---|
| **OpenAI** (default) | `gpt-image-1` | ~10-15s per image | API credits |
| **Ollama** (local) | Flux2 / any model | ~60-180s per image | Free (local GPU) |

Images are saved to disk for persistence and embedded as inline base64 data URIs in the generated code so they render correctly in Sandpack's browser sandbox.

---

## Deployment

### Docker Compose (Recommended)

```bash
./deploy.sh              # Build and start all services
./deploy.sh logs         # Tail live logs
./deploy.sh stop         # Stop all services
./deploy.sh clean        # Stop and remove all data
```

Services: `redis` (7-alpine), `backend` (Python 3.13), `frontend` (Node 22).
Health checks on all services. Persistent volumes for Redis data and SQLite.

### Local Development

```bash
./deploy.sh local        # Starts backend (:8000) + frontend (:3000)
```

Requires Python 3.11+, Node.js 18+, and optionally Redis.

### Manual Setup

**Backend:**
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env     # Set OPENAI_API_KEY
uvicorn app.api.main:app --reload --port 8000
```

**Frontend:**
```bash
cd frontend
npm ci
npm run dev              # http://localhost:3000
```

---

## Configuration

### Backend (`backend/.env`)

| Variable | Default | Description |
|---|---|---|
| `OPENAI_API_KEY` | *required* | OpenAI API key |
| `LLM_MODEL` | `gpt-5.1` | Primary generation model |
| `LLM_MODEL_SMALL` | `gpt-5-mini-2025-08-07` | Planning / validation model |
| `CORS_ORIGINS` | `http://localhost:3000` | Allowed CORS origins |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection (optional) |
| `DATABASE_PATH` | `data/agentic.db` | SQLite database path |
| `IMAGE_STORAGE_PATH` | `data/images` | Generated image storage |
| `IMAGE_PROVIDER` | `openai` | Image generation provider (`openai` or `ollama`) |
| `IMAGE_MODEL` | `gpt-image-1` | Image model (`gpt-image-1` for OpenAI, model name for Ollama) |
| `IMAGE_SIZE` | `1024x1024` | OpenAI image size |
| `IMAGE_QUALITY` | `medium` | OpenAI image quality (`low`, `medium`, `high`) |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL (only if `IMAGE_PROVIDER=ollama`) |
| `WS_AUTH_KEY` | *(empty)* | Bearer token for API auth (optional) |
| `LOG_FORMAT` | `dev` | `dev` (colored) or `json` (structured) |
| `SESSION_CACHE_TTL` | `3600` | Redis session cache TTL in seconds |

### Frontend

| Variable | Default | Description |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Backend API URL |
| `NEXT_PUBLIC_AUTH_TOKEN` | *(empty)* | Bearer token (must match `WS_AUTH_KEY`) |

---

## Project Structure

```
agentic-ui/
├── deploy.sh                        # One-command deploy script
├── docker-compose.yml               # Multi-service orchestration
├── .github/workflows/ci.yml         # GitHub Actions CI pipeline
│
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── .env.example
│   ├── app/
│   │   ├── agents/
│   │   │   ├── graph.py             # LangGraph state graph
│   │   │   ├── planner.py           # Intent detection + file planning
│   │   │   ├── file_generator.py    # Parallel per-file code generation
│   │   │   ├── image_generator.py   # Ollama image generation
│   │   │   ├── validator.py         # Error fixing with retry loop
│   │   │   ├── state.py             # AgentState TypedDict
│   │   │   └── utils.py             # JSON extraction, retry decorator
│   │   ├── api/
│   │   │   └── main.py              # FastAPI app, SSE endpoint, auth
│   │   ├── core/
│   │   │   ├── config.py            # Pydantic BaseSettings
│   │   │   ├── llm.py               # Singleton LLM factory
│   │   │   ├── redis_client.py      # Redis with graceful degradation
│   │   │   ├── database.py          # SQLite (WAL) + connection pool
│   │   │   ├── memory.py            # Redis + SQLite unified facade
│   │   │   ├── logger.py            # Dual-mode logging + correlation IDs
│   │   │   └── enums.py             # StrEnum types
│   │   ├── prompts/
│   │   │   ├── __init__.py          # Template loader with lru_cache
│   │   │   ├── planner.md           # Planner system prompt
│   │   │   ├── file_generator.md    # File generator system prompt
│   │   │   └── validator.md         # Validator system prompt
│   │   └── templates/
│   │       └── starter.py           # Default App.tsx
│   └── tests/
│       ├── test_utils.py
│       ├── test_database.py
│       └── test_enums.py
│
└── frontend/
    ├── Dockerfile
    ├── package.json
    ├── .prettierrc
    └── src/
        ├── app/
        │   ├── page.tsx              # Main IDE layout (3-pane split)
        │   └── layout.tsx            # Root layout
        ├── components/
        │   ├── LivePreview.tsx        # Sandpack browser preview
        │   ├── ChatPanel.tsx          # Chat UI + agent steps + cancel
        │   ├── CodeEditor.tsx         # Code viewer with file tabs
        │   └── ErrorBoundary.tsx      # Per-panel error boundary
        ├── hooks/
        │   └── useChat.ts            # SSE streaming + AbortController
        └── lib/
            └── store.ts              # Zustand + localStorage persistence
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 15 (App Router), Tailwind CSS, Zustand |
| Browser Preview | Sandpack (`@codesandbox/sandpack-react`) |
| Real-time Streaming | Server-Sent Events (SSE) |
| Backend | FastAPI + Uvicorn, Python 3.13 |
| Agent Orchestration | LangGraph (parallel `Send` fan-out) |
| LLM | OpenAI GPT-5.1 / GPT-5-mini via LangChain |
| Image Generation | OpenAI `gpt-image-1` (default) or Ollama (local) |
| Cache | Redis 7 (optional, graceful degradation) |
| Database | SQLite (WAL mode, async via aiosqlite) |
| CI/CD | GitHub Actions |
| Containerization | Docker Compose |

---

## State Graph

```
START
  |
  v
planner ------------------------------------------------> assembler
  |  (intent=fix or file_plan=[])                            ^
  |                                                          |
  +-- Send(file_generator, file1)  ------------------------> |
  +-- Send(file_generator, file2)  ------------------------> |  (parallel)
  +-- Send(file_generator, fileN)  ------------------------> |
  +-- Send(image_generator, img1)  ------------------------> |
                                                             |
                                                         validator
                                                        /         \
                                                (no errors)   (errors, retry<3)
                                                    |               |
                                                   END          planner (retry)
```

---

## Logs

### Development Mode (`LOG_FORMAT=dev`)

```
2026-03-20 14:23:01.456 | INFO  | main           | Pipeline start -> "build a dashboard..."
2026-03-20 14:23:01.891 | INFO  | planner        | Planning -> intent=create | 3 files
2026-03-20 14:23:02.346 | INFO  | file_generator | Generating -> App.tsx (parallel)
2026-03-20 14:23:02.346 | INFO  | file_generator | Generating -> components/Chart.tsx (parallel)
2026-03-20 14:23:06.789 | INFO  | file_generator | Done 4.44s -> App.tsx (312 chars)
2026-03-20 14:23:07.103 | INFO  | assembler      | Assembled 3 file(s)
2026-03-20 14:23:07.104 | INFO  | validator      | No errors -> approved
2026-03-20 14:23:07.105 | INFO  | main           | Pipeline finished in 5.21s
```

### Production Mode (`LOG_FORMAT=json`)

```json
{"timestamp":"2026-03-20T14:23:01.456Z","level":"INFO","logger":"main","message":"Pipeline start","correlation_id":"a1b2c3"}
```

---

## License

MIT
