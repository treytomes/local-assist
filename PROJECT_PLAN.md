# Local Assist — Project Plan

A Gemini-like desktop assistant built on Azure AI services with local Ollama fallback,
modelled on the code-pad UX (React + Electron + Ant Design + Tailwind, VS Code dark theme).

---

## Confirmed Azure Services (georg-m3z0unyq-eastus2, API key auth)

| Capability        | Model                  | Deployment status              |
|-------------------|------------------------|--------------------------------|
| Chat (primary)    | `gpt-5.3-chat`         | Deployed ✓                     |
| Chat (switchable) | `Mistral-Large-3`      | Deployed ✓                     |
| Text → Speech     | `gpt-4o-mini-tts`      | Deployed ✓ (all voices tested) |
| Speech → Text     | `gpt-4o-transcribe`    | Deployed ✓                     |
| Vision            | `gpt-4o`               | Deployed ✓ (vision confirmed)  |
| Realtime voice    | `gpt-realtime`         | Deployed ✓ (replaces retired `gpt-4o-realtime-preview`) |

**TTS voices (all confirmed working):** alloy · echo · fable · onyx · nova · shimmer
— configurable at runtime in Settings.

**Note:** No dedicated Azure AI Vision (Computer Vision/Florence) resource found — image
understanding will be handled by vision-capable chat models.

## Web Search

Tavily Search API — free tier (1k calls/month) for development.
`TAVILY_API_KEY` added to `.env`.

---

## Tech Stack

| Layer         | Technology                                              |
|---------------|---------------------------------------------------------|
| Desktop shell | Electron 33                                             |
| Frontend      | React 19 + TypeScript + Vite 6                          |
| UI components | Ant Design 5 + Tailwind CSS 4                           |
| State         | Zustand 5 (with `persist` middleware)                   |
| Local DB      | better-sqlite3 (conversations, cost tracking, RAG)      |
| Vector store  | sqlite-vec (RAG memory, embedded in same DB file)       |
| IPC           | Context-bridged `window.electronAPI`                    |
| Backend       | FastAPI (Python) — sidecar process spawned by Electron  |
| Tool protocol | MCP via `mcp[cli]` — FastMCP mounted as ASGI sub-app    |
| Voice I/O     | Azure TTS/STT via HTTP; Realtime via WebSocket          |

---

## Decisions Made

| Topic | Decision |
|---|---|
| Chat models | Switch between `gpt-5.3-chat` and `Mistral-Large-3` (both deployed) |
| Model switching | Per-conversation toggle in UI header, with live cost-per-token display |
| TTS voice | Configurable at runtime (Settings); all 6 voices available |
| Search | Tavily, free tier for development |
| Conversation history | Persistent list, kept indefinitely in SQLite |
| Context window | Rolling window (configurable depth, e.g. last 20 messages sent to model) |
| Cross-conversation memory | RAG via sqlite-vec — past conversations embedded and retrieved at session start |
| Cost visibility | Running cost ticker per conversation + cost report comparing gpt-5.3-chat vs Mistral-Large-3 |
| Tool use | OpenAI function-calling format; non-streaming first call detects tool_calls, executes, then streams final answer |
| MCP | FastAPI backend doubles as MCP server at `/mcp` via `streamable_http_app()` |
| Assistant persona | Named "Mara" — configurable system prompt, persisted to localStorage |
| Inference params | Per-model (temperature, max tokens, context window), persisted to localStorage |

---

## Milestones

### M1 — Backend foundation ✅
**Goal:** Running FastAPI sidecar with provider routing, cost tracking, and RAG memory.

- [x] Scaffold `src/backend/` FastAPI app
- [x] `/v1/chat/completions` — OpenAI-compatible, streams tokens, records usage
- [x] `/v1/health` — Azure reachability check (drives Ollama fallback)
- [x] SQLite schema:
  - `conversations` — id, title, created_at, updated_at, model, provider
  - `messages` — id, conversation_id, role, content, timestamp, model
  - `usage` — id, conversation_id, message_id, provider, model, prompt_tokens, completion_tokens, cost_usd, timestamp
  - `pricing` — provider, model, input_cost_per_1k, output_cost_per_1k, last_updated (seeded at startup)
  - `embeddings` — id, conversation_id, chunk_text, vector (sqlite-vec column)
- [x] `/v1/usage` — cost summary (per conversation, daily, by model comparison)
- [x] `/v1/pricing` — list all pricing rows; `GET /v1/pricing/{provider}/{model}` fetch one; `POST` upsert (manual rate override)
- [x] Pricing seed: all 9 deployed models with verified retail rates
- [x] RAG: embed conversation summaries at close; retrieve top-k at new conversation start; chunks injected as system message prefix on each chat turn
- [x] Rolling context window: configurable depth (default 20 messages) truncated before sending to model; leading system message always preserved
- [x] `PATCH /v1/conversations/{id}` — update title and/or model on an existing conversation
- [x] `DELETE /v1/conversations/{id}/messages/{msg_id}` — remove individual messages
- [x] Ollama fallback: if Azure unreachable, auto-pull `gemma3:1b` if not already present
- [x] Add `TAVILY_API_KEY` to `.env`
- [x] Unit + integration test suite — 185 collected, 120 unit, 96% coverage; `./test.sh` / `./test.sh --integration` / `./test.sh --azure`
- [x] MCP server: FastAPI backend mounts `FastMCP` at `/mcp` (`streamable_http_app()`)
  - `get_datetime` tool — current date/time/timezone with optional IANA tz override
  - `get_system_info` tool — OS, CPU (model, cores, per-core usage%), RAM/swap, GPU (nvidia-smi → rocm-smi → lspci), system model via DMI
- [x] Tool-use loop in `/v1/chat/completions`: non-streaming probe call → execute any tool_calls → stream final response
- [x] `is_retry` flag to prevent duplicate user message persistence on retry

### M2 — Electron shell + chat UI ✅
**Goal:** Working desktop app matching code-pad visual style.

- [x] Init Electron project (electron-vite 3, React 19, TypeScript 5, Vite 6)
- [x] VS Code dark theme CSS variables + Ant Design 5 dark algorithm token overrides
- [x] Diagnostic Dashboard tab:
  - Provider health panel — Azure + Ollama status, 30s auto-refresh, manual refresh
  - API tester — preset dropdown (all endpoints, grouped), path variable substitution, method/body editor, live response viewer with status + elapsed time
- [x] Tabbed shell — Diagnostic Dashboard pinned as first tab; Chat as second tab
- [x] 3-panel chat layout:
  - **Left sidebar** — conversation list (search, rename, delete); new conversation button; auto-scroll; active highlight; relative timestamps; last-used conversation restored on reload
  - **Main panel** — chat thread: message bubbles (user right/blue, assistant left), timestamps, streaming cursor, retry button on last user message, per-message delete
  - **Right panel** (collapsible) — conversation cost + token counts; provider health tags
- [x] Message composer: auto-growing textarea, Enter to send / Shift+Enter for newline, model selector dropdown, streaming loading state
- [x] Model switcher: `gpt-5.3-chat` ↔ `Mistral-Large-3` dropdown; PATCH persists to backend
- [x] Settings modal (gear icon):
  - **Models tab** — per-model: temperature (hidden for gpt-5.3-chat), max tokens, context window depth; draft state committed on Save
  - **System Prompt tab** — free-text; defaults to Mara persona prompt
- [x] Context Inspector drawer (bug icon) — Connection, Model Parameters, Available Tools, full reconstructed message list with context window truncation preview
- [x] Auto-title: first user message (≤60 chars) used as conversation title; patched to backend
- [x] Retry: re-sends last user message, discards last assistant turn from history and DB, avoids stale closure via `historyOverride` parameter
- [x] Settings and active conversation persisted to localStorage (Zustand `persist` middleware)

### M3 — Speech I/O (Week 2–3)
**Goal:** Voice in, voice out via Azure.

- [ ] STT: stream mic audio → Azure `gpt-4o-transcribe` → text
- [ ] TTS: assistant reply → Azure `gpt-4o-mini-tts` → audio playback
- [ ] Voice selection passed as parameter (alloy/echo/fable/onyx/nova/shimmer)
- [ ] Expose audio via IPC: `start-listening`, `stop-listening`, `speak`, `stop-speaking`
- [ ] Push-to-talk mode (hold key) and continuous mode toggle

### M4 — Vision (Week 3)
**Goal:** Send images, get analysis back.

- [ ] Image attach: drag-drop or file picker → base64 → multimodal message
- [ ] Screenshot capture shortcut (Electron `desktopCapturer`)
- [ ] Image displayed inline in thread

### M5 — Web search tool (Week 3)
**Goal:** Assistant can look up current information.

- [ ] Tavily tool call in backend (`tools/search.py`)
- [ ] Tool result injected into context; shown as citation card in thread UI
- [ ] "Searched for X" inline indicator in message bubble

### M6 — Google account tools (Week 4)
**Goal:** Read/write calendar, tasks, Drive.

- [ ] Google OAuth flow in Electron main process (open browser, capture redirect)
- [ ] Token stored via Electron `safeStorage` (encrypted at rest)
- [ ] Function-call tools:
  - `get_calendar_events(date_range)`
  - `create_calendar_event(title, time, description)`
  - `get_tasks(list_id?)`
  - `create_task(title, due_date?)`
  - `search_drive(query)` — metadata only
- [ ] Tool invocations shown inline ("Checking your calendar…")

### M7 — Cost dashboard (Week 4)
**Goal:** Measurable, comparable cost per model and provider.

- [ ] Right panel: live cost ticker (current conversation)
- [ ] Model comparison table: `gpt-5.3-chat` vs `Mistral-Large-3` — cost per 1k tokens, total spent, avg per conversation
- [ ] Daily/weekly spend chart (Recharts)
- [ ] Per-provider breakdown
- [ ] Cost alert: notify if session exceeds configurable threshold ($)
- [ ] Export usage as CSV

### M8 — Polish + packaging (Week 5)
**Goal:** Installable app.

- [ ] System tray icon with quick-ask popup
- [ ] Global hotkey to open/focus window
- [ ] Settings modal: provider priority, default model, TTS voice, theme, cost alert threshold
- [ ] Bundle `.venv` into packaged app via electron-builder `extraResources`; validate that `sqlite-vec` native extension survives (consider PyInstaller sidecar as alternative if `.so` loading breaks)
- [ ] electron-builder: Linux AppImage + Windows NSIS + macOS DMG
- [ ] Auto-update scaffold (electron-updater)

---

## Project Structure

```
~/projects/local-assist/
├── src/
│   ├── renderer/                  # React UI (Vite, renderer process)
│   │   ├── components/
│   │   │   ├── DiagnosticDashboard.tsx  ✓
│   │   │   ├── ChatView.tsx             ✓  3-panel layout + send/retry/delete logic
│   │   │   ├── ChatThread.tsx           ✓  message bubbles, streaming cursor
│   │   │   ├── MessageComposer.tsx      ✓  textarea, model selector, send button
│   │   │   ├── ConversationList.tsx     ✓  search, rename, delete, active state
│   │   │   ├── RightPanel.tsx           ✓  cost + provider health
│   │   │   ├── SettingsModal.tsx        ✓  per-model params + system prompt
│   │   │   └── ContextInspector.tsx     ✓  debug drawer
│   │   ├── styles/index.css       ✓ VS Code dark theme + Tailwind v4
│   │   ├── store.ts               ✓ Zustand 5 store + persist middleware
│   │   ├── electron.d.ts          ✓ window.electronAPI types
│   │   ├── index.html             ✓
│   │   ├── main.tsx               ✓ React entry
│   │   └── App.tsx                ✓ AntD ConfigProvider dark theme + Tabs
│   ├── main/
│   │   ├── index.ts               ✓ Electron main + IPC + sidecar spawn
│   │   ├── audio.ts               # TTS/STT bridge (M3)
│   │   └── google-auth.ts         # OAuth flow (M6)
│   ├── preload/index.ts           ✓ contextBridge → window.electronAPI
│   ├── backend/                   # FastAPI sidecar (Python)
│   │   ├── main.py                ✓ routes, tool-use loop, MCP mount
│   │   ├── router.py              ✓ provider routing + call_with_tools
│   │   ├── mcp_server.py          ✓ FastMCP — get_datetime, get_system_info
│   │   ├── rag.py                 ✓ sqlite-vec embed + retrieve
│   │   ├── cost.py                ✓ usage recording + reporting
│   │   ├── database.py            ✓ schema, migrations, CRUD
│   │   ├── providers/
│   │   │   ├── azure.py           ✓ streaming + tool call support
│   │   │   └── ollama.py          ✓ streaming + tool call support
│   │   └── tools/
│   │       ├── datetime_tool.py   ✓ current date/time/timezone
│   │       ├── system_info_tool.py ✓ CPU/RAM/GPU/OS snapshot
│   │       ├── search.py          # Tavily (M5)
│   │       └── google.py          # Calendar / Tasks / Drive (M6)
│   └── shared/types.ts            ✓ Conversation, Message, ModelId, etc.
├── .env
├── package.json                   ✓
├── requirements.txt               ✓
├── tsconfig.json                  ✓ project references
├── tsconfig.node.json             ✓ main + preload
├── tsconfig.web.json              ✓ renderer
├── electron.vite.config.ts        ✓
└── electron-builder.config.ts     ✓
```
