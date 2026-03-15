# Agentic Web IDE

A Replit-style browser IDE where AI agents generate React + Tailwind code rendered live in a Sandpack preview. Describe a UI in plain English and watch it appear instantly — no setup, no build tools, no deployments.

---

## How It Works

```
User types prompt
      │
      ▼
  FastAPI WebSocket
      │
      ▼
┌─────────────────────────────────────────────────────────┐
│                  LangGraph Pipeline                      │
│                                                         │
│   planner ──► Send fan-out ──► file_generator × N       │
│   (gpt-4o-mini)    │           (gpt-4o, parallel)       │
│                    │                   │                 │
│                    └───────────────────┘                 │
│                            ▼                             │
│                        assembler                         │
│                            ▼                             │
│                        validator ──► retry (max 3)       │
│                            │                             │
│                           END                            │
└─────────────────────────────────────────────────────────┘
      │
      ▼
  WebSocket stream (status + files)
      │
      ▼
  Sandpack (react-ts template, browser bundler)
  Live preview updates in real-time
```

---

## Architecture

### Backend — Python / FastAPI

#### Agent Pipeline (`backend/app/agents/`)

| File | Role | Model |
|---|---|---|
| `planner.py` | Decides intent (`create`/`modify`/`fix`) and produces a file plan (paths + descriptions). No code written here. | gpt-4o-mini |
| `file_generator.py` | One instance per file, all run **in parallel** via LangGraph `Send` API. Generates complete React/TypeScript files. | gpt-4o |
| `graph.py` | Wires the LangGraph state graph: `planner → Send fan-out → assembler → validator`. | — |
| `validator.py` | Receives compilation errors from the frontend, makes surgical fixes. Retries up to 3 times. | gpt-4o-mini |
| `state.py` | `AgentState` TypedDict — the single source of truth flowing through the graph. Uses `operator.add` annotated fields for parallel accumulation. | — |
| `utils.py` | `extract_json()` (robust JSON extractor from LLM output) and `@retry_on_error` decorator. | — |

#### Core (`backend/app/core/`)

| File | Purpose |
|---|---|
| `llm.py` | Singleton LLM cache. One `ChatOpenAI` instance per `(provider, tier, temperature, streaming)` — no redundant API client creation. |
| `logger.py` | Colored structured logging with timestamps (ms precision), module name shortening, and a `Timer` class for per-operation elapsed time. |
| `config.py` | Pydantic settings loaded from `.env` (`OPENAI_API_KEY`, `LLM_MODEL`, `CORS_ORIGINS`). |

#### API (`backend/app/api/main.py`)

- `GET /health` — health check
- `GET /api/template` — returns the starter `App.tsx` file
- `WS /ws/chat` — real-time bidirectional pipeline communication

WebSocket features:
- **Heartbeat** — sends a ping every 5s during LLM generation to prevent browser timeout
- **Safe send** — catches `WebSocketDisconnect` gracefully instead of crashing
- **Stream mode** — uses LangGraph `astream(stream_mode="updates")` to emit per-node status updates as they complete

#### Templates (`backend/app/templates/`)

- `starter.py` — minimal `App.tsx` loaded on IDE startup (Sandpack `react-ts` compatible)

---

### Frontend — Next.js / TypeScript

#### Components (`frontend/src/components/`)

| File | Purpose |
|---|---|
| `LivePreview.tsx` | Sandpack `react-ts` template with browser bundler (no server required). Forces remount via `key={previewKey}` when file set changes. Injects Tailwind via CDN `externalResources`. |
| `ChatPanel.tsx` | Conversational UI — user prompt input, message history, streaming agent step display. |
| `CodeEditor.tsx` | Syntax-highlighted code viewer for generated files with file tab switching. |

#### State (`frontend/src/lib/store.ts`)

Zustand store with:

```ts
{
  messages: ChatMessage[]       // chat history
  agentSteps: AgentStep[]       // live pipeline step feed
  files: Record<string, string> // generated file contents
  activeFile: string            // currently viewed file
  isGenerating: boolean         // pipeline running flag
  compilationErrors: string[]   // Sandpack runtime errors
}
```

#### Hooks (`frontend/src/hooks/useChat.ts`)

Manages the WebSocket lifecycle — connects, sends prompts, dispatches incoming `status`/`result`/`error` messages to the Zustand store.

#### Pages

- `src/app/page.tsx` — main IDE layout (chat + code editor + live preview split pane)
- `src/app/layout.tsx` — root layout, no COEP/COOP headers (required for Sandpack bundler iframe)

---

## Parallel File Generation

When the planner outputs a multi-file plan (e.g. `App.tsx` + `components/Form.tsx` + `components/Header.tsx`), LangGraph's `Send` API dispatches one `file_generator` node per file — all running **simultaneously**:

```python
# graph.py — route_planner
return [
    Send("file_generator", {**state, "current_file": file_info})
    for file_info in file_plan
]
```

Generation time for N files ≈ generation time for 1 file. Each generator receives the full file plan as context so it can write correct relative import paths without seeing other files' code.

Results are accumulated via `operator.add` on the `generated_file_parts` field, then merged by the `assembler` node.

---

## State Graph

```
START
  │
  ▼
planner  ──────────────────────────────────────► assembler
  │  (intent=fix or file_plan=[])                    ▲
  │                                                  │
  └── Send(file_generator, file1)  ────────────────► │
  └── Send(file_generator, file2)  ────────────────► │  (parallel)
  └── Send(file_generator, fileN)  ────────────────► │
                                                      │
                                                  validator
                                                  /        \
                                          (no errors)   (errors, retry<3)
                                              │                │
                                             END           planner (retry loop)
```

---

## Sandpack Integration

Sandpack uses the `react-ts` template (browser bundler — no Node.js server):

- **Entry file**: `/App.tsx` (root level — not `/src/App.tsx`)
- **Components**: `components/X.tsx`
- **Tailwind CSS**: injected via `externalResources: ["https://cdn.tailwindcss.com"]`
- **Remount strategy**: `key={previewKey}` on `SandpackProvider` forces full re-initialization when the generated file set changes
- **No COEP headers**: removed from `next.config.ts` — `require-corp` blocked the Sandpack bundler iframe

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend framework | Next.js 14 (App Router) |
| UI components | Tailwind CSS |
| State management | Zustand |
| Browser preview | Sandpack (`@codesandbox/sandpack-react` v2.20) |
| Real-time comms | WebSocket (native browser API) |
| Backend framework | FastAPI + Uvicorn |
| Agent orchestration | LangGraph |
| LLM client | LangChain OpenAI (`langchain-openai`) |
| LLM models | gpt-4o (generation), gpt-4o-mini (planning/validation) |
| Language | Python 3.13 / TypeScript |

---

## Local Setup

### Prerequisites

- Python 3.11+
- Node.js 18+
- OpenAI API key

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Create .env
cp .env.example .env
# Set OPENAI_API_KEY in .env

uvicorn app.api.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
# Runs at http://localhost:3000
```

### Environment Variables

**`backend/.env`**

```env
OPENAI_API_KEY=sk-...
LLM_MODEL=gpt-4o
LLM_PROVIDER=openai
CORS_ORIGINS=["http://localhost:3000"]
```

**`frontend/.env.local`**

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

---

## Project Structure

```
agentic-ui/
├── backend/
│   ├── app/
│   │   ├── agents/
│   │   │   ├── graph.py          # LangGraph state graph definition
│   │   │   ├── planner.py        # File plan generation (gpt-4o-mini)
│   │   │   ├── file_generator.py # Parallel per-file code generation (gpt-4o)
│   │   │   ├── validator.py      # Error fixing with retry loop
│   │   │   ├── state.py          # AgentState TypedDict
│   │   │   └── utils.py          # JSON extraction, retry decorator
│   │   ├── api/
│   │   │   └── main.py           # FastAPI app, WebSocket endpoint
│   │   ├── core/
│   │   │   ├── llm.py            # Singleton LLM factory + cache
│   │   │   ├── logger.py         # Structured colored logging
│   │   │   └── config.py         # Pydantic settings
│   │   └── templates/
│   │       └── starter.py        # Default App.tsx starter
│   └── requirements.txt
└── frontend/
    └── src/
        ├── app/
        │   ├── page.tsx           # Main IDE layout
        │   └── layout.tsx         # Root layout (no COEP headers)
        ├── components/
        │   ├── LivePreview.tsx    # Sandpack browser preview
        │   ├── ChatPanel.tsx      # Chat UI + agent step feed
        │   └── CodeEditor.tsx     # Generated code viewer
        ├── hooks/
        │   └── useChat.ts         # WebSocket hook
        └── lib/
            └── store.ts           # Zustand global state
```

---

## Logs

The backend emits structured colored logs for every pipeline step:

```
2026-03-15 14:23:01.456 | INFO     | main               | Pipeline start → "build a job application form…"
2026-03-15 14:23:01.891 | INFO     | planner            | Planning → prompt: "build a job application form..."
2026-03-15 14:23:02.344 | INFO     | planner            | Done in 0.45s | intent=create | files=['App.tsx', 'components/JobForm.tsx']
2026-03-15 14:23:02.345 | INFO     | graph              | route_planner → Send x2 parallel generators
2026-03-15 14:23:02.346 | INFO     | file_generator     | Generating → App.tsx | "Root component that imports JobForm"
2026-03-15 14:23:02.346 | INFO     | file_generator     | Generating → components/JobForm.tsx | "Form with all fields"
2026-03-15 14:23:06.789 | INFO     | file_generator     | Done in 4.44s → App.tsx (312 chars)
2026-03-15 14:23:07.102 | INFO     | file_generator     | Done in 4.76s → components/JobForm.tsx (1843 chars)
2026-03-15 14:23:07.103 | INFO     | graph              | Assembled 2 file(s) in 0.0s → ['App.tsx', 'components/JobForm.tsx']
2026-03-15 14:23:07.104 | INFO     | validator          | Validator: no errors → approved ✓
2026-03-15 14:23:07.105 | INFO     | main               | Pipeline finished in 5.21s ✓
```
