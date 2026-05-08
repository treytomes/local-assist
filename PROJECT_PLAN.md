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

## Tech Stack (matching code-pad)

| Layer         | Technology                                              |
|---------------|---------------------------------------------------------|
| Desktop shell | Electron 30                                             |
| Frontend      | React 19 + TypeScript + Vite 6                          |
| UI components | Ant Design 6 + Tailwind CSS 4                           |
| State         | Zustand 5                                               |
| Local DB      | better-sqlite3 (conversations, cost tracking, RAG)      |
| Vector store  | sqlite-vec (RAG memory, embedded in same DB file)       |
| IPC           | Context-bridged `window.electronAPI`                    |
| Backend       | FastAPI (Python) — sidecar process spawned by Electron  |
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

---

## Milestones

### M1 — Backend foundation ✅
**Goal:** Running FastAPI sidecar with provider routing, cost tracking, and RAG memory.

- [x] Scaffold `src/backend/` FastAPI app
- [x] `/v1/chat/completions` — OpenAI-compatible, streams tokens, records usage
- [x] `/v1/health` — Azure reachability check (drives Ollama fallback)
- [x] SQLite schema:
  - `conversations` — id, title, created_at, updated_at, model, provider
  - `messages` — id, conversation_id, role, content, timestamp
  - `usage` — id, conversation_id, message_id, provider, model, prompt_tokens, completion_tokens, cost_usd, timestamp
  - `pricing` — provider, model, input_cost_per_1k, output_cost_per_1k, last_updated (seeded at startup)
  - `embeddings` — id, conversation_id, chunk_text, vector (sqlite-vec column)
- [x] `/v1/usage` — cost summary (per conversation, daily, by model comparison)
- [x] `/v1/pricing` — list all pricing rows; `GET /v1/pricing/{provider}/{model}` fetch one; `POST` upsert (manual rate override)
- [x] Pricing seed: all 9 deployed models with verified retail rates (gpt-5.3-chat and Mistral-Large-3 estimated; updatable via POST)
- [x] RAG: embed conversation summaries at close; retrieve top-k at new conversation start; chunks injected as system message prefix on each chat turn
- [x] Rolling context window: configurable depth (default 20 messages) truncated before sending to model; leading system message always preserved
- [x] `PATCH /v1/conversations/{id}` — update title and/or model on an existing conversation
- [x] Ollama fallback: if Azure unreachable, auto-pull `gemma3:1b` if not already present
- [x] Add `TAVILY_API_KEY` to `.env`
- [x] Unit + integration test suite — 185 collected, 120 unit, 96% coverage; `./test.sh` / `./test.sh --integration` / `./test.sh --azure`

### M2 — Electron shell + chat UI (Week 2)
**Goal:** Working desktop app matching code-pad visual style.

- [x] Init Electron project (electron-vite 3, React 19, TypeScript 5, Vite 6)
- [x] VS Code dark theme CSS variables + Ant Design 5 dark algorithm token overrides
- [x] Diagnostic Dashboard (first screen):
  - Provider health panel — Azure + Ollama status, 30s auto-refresh, manual refresh
  - API tester — preset dropdown, method/path/body editor, live response viewer with status + elapsed time
- [ ] 3-panel layout:
  - **Left sidebar** — conversation list (search, star, rename, delete); new conversation button
  - **Main panel** — chat thread: message bubbles, timestamps, model+provider badge per message, streaming token rendering
  - **Right panel** (collapsible) — cost dashboard + provider status indicators
- [ ] Message composer: text input + mic button + image attach + send
- [ ] Model switcher in header: `gpt-5.3-chat` ↔ `Mistral-Large-3` toggle with per-model cost display (uses `PATCH /v1/conversations/{id}`)
- [ ] Rolling context window depth setting (default: 20 messages, configurable via `context_window` chat param)

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
- [ ] Settings modal: provider priority, default model, TTS voice, rolling window depth, theme, cost alert threshold
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
│   │   │   ├── ChatThread.tsx
│   │   │   ├── MessageComposer.tsx
│   │   │   ├── ConversationList.tsx
│   │   │   ├── ModelSwitcher.tsx
│   │   │   ├── CostDashboard.tsx
│   │   │   └── SettingsModal.tsx
│   │   ├── styles/index.css       ✓ VS Code dark theme + Tailwind v4
│   │   ├── store.ts               ✓ Zustand 5 store
│   │   ├── electron.d.ts          ✓ window.electronAPI types
│   │   ├── index.html             ✓
│   │   ├── main.tsx               ✓ React entry
│   │   └── App.tsx                ✓ AntD ConfigProvider dark theme
│   ├── main/
│   │   ├── index.ts               ✓ Electron main + IPC + sidecar spawn
│   │   ├── audio.ts               # TTS/STT bridge (M3)
│   │   └── google-auth.ts         # OAuth flow (M6)
│   ├── preload/index.ts           ✓ contextBridge → window.electronAPI
│   ├── backend/                   # FastAPI sidecar (Python) ✓ M1 complete
│   │   ├── main.py
│   │   ├── router.py
│   │   ├── rag.py
│   │   ├── cost.py
│   │   ├── database.py
│   │   ├── providers/
│   │   │   ├── azure.py
│   │   │   └── ollama.py
│   │   └── tools/
│   │       ├── search.py          # Tavily (M5)
│   │       └── google.py          # Calendar / Tasks / Drive (M6)
│   └── shared/types.ts            ✓ HealthStatus, ApiResponse, etc.
├── .env
├── package.json                   ✓
├── tsconfig.json                  ✓ project references
├── tsconfig.node.json             ✓ main + preload
├── tsconfig.web.json              ✓ renderer
├── electron.vite.config.ts        ✓
└── electron-builder.config.ts     ✓
```
