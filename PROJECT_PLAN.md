# Local Assist — Project Plan

A Gemini-like desktop assistant built on Azure AI (Mistral Large 3), modelled on the VS Code dark UX (React + Electron + Ant Design).

---

## Confirmed Azure Services (georg-m3z0unyq-eastus2, API key auth)

| Capability        | Model                  | Deployment status              |
|-------------------|------------------------|--------------------------------|
| Chat (primary)    | `Mistral-Large-3`      | Deployed ✓                     |
| Text → Speech     | `gpt-4o-mini-tts`      | Deployed ✓ (all voices tested) |
| Speech → Text     | `gpt-4o-transcribe`    | Deployed ✓                     |
| Vision            | `gpt-4o`               | Deployed ✓ (vision confirmed)  |
| Realtime voice    | `gpt-realtime`         | Deployed ✓                     |

**TTS voices (all confirmed working):** alloy · echo · fable · onyx · nova · shimmer

**Note:** No dedicated Azure AI Vision resource — image understanding handled by vision-capable chat models.

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
| Vector store  | sqlite-vec (RAG memory + knowledge graph, embedded DB)  |
| IPC           | Context-bridged `window.electronAPI`                    |
| Backend       | FastAPI (Python) — sidecar process spawned by Electron  |
| Tool protocol | MCP via `mcp[cli]` — FastMCP mounted as ASGI sub-app    |

---

## Decisions Made

| Topic | Decision |
|---|---|
| Chat model | `Mistral-Large-3` exclusively (Azure deployment) |
| Ollama fallback | `gemma3:1b` auto-pulled when Azure is unreachable |
| TTS voice | Configurable at runtime (Settings); all 6 voices available |
| Search | Tavily, free tier for development |
| Conversation history | Persistent list, kept indefinitely in SQLite |
| Context window | Rolling window (configurable depth, default 20 messages) |
| Cross-conversation memory | RAG via sqlite-vec — past responses embedded and retrieved |
| Knowledge graph memory | S/P/O triples with TTL decay, pinning, and vector semantic search |
| Cost visibility | Per-conversation cost + token counts in right panel |
| Tool use | OpenAI function-calling format; non-streaming probe → execute → stream |
| MCP | FastAPI backend doubles as MCP server at `/mcp` via `streamable_http_app()` |
| Assistant persona | Named "Mara" — configurable system prompt, persisted to localStorage |
| Inference params | Temperature, max tokens, context window — persisted to localStorage |
| Message rendering | Markdown with syntax highlighting (`react-markdown` + `rehype-highlight`) |
| Tokenizer | Tekken v3 (131k vocab, tiktoken) — actual Mistral Large 3 tokenizer |
| macOS packaging | Out of scope — no Mac build target |

---

## Milestones

### M1 — Backend foundation ✅
**Goal:** Running FastAPI sidecar with provider routing, cost tracking, and RAG memory.

- [x] Scaffold `src/backend/` FastAPI app
- [x] `/v1/chat/completions` — OpenAI-compatible, streams tokens, records usage
- [x] `/v1/health` — Azure reachability check (drives Ollama fallback)
- [x] SQLite schema: `conversations`, `messages`, `usage`, `pricing`, `embeddings`
- [x] `/v1/usage` — cost summary (per conversation, daily, by model)
- [x] `/v1/pricing` — list/fetch/upsert pricing rows
- [x] Pricing seed: deployed models with verified retail rates
- [x] RAG: embed assistant replies; retrieve top-k at each chat turn; injected as system prefix
- [x] Rolling context window: configurable depth, leading system message always preserved
- [x] `PATCH /v1/conversations/{id}` — update title and/or model
- [x] `DELETE /v1/conversations/{id}/messages/{msg_id}` — remove individual messages
- [x] Ollama fallback: if Azure unreachable, auto-pull `gemma3:1b`
- [x] Unit + integration test suite — 185 collected, 96% coverage; `./test.sh`
- [x] MCP server mounted at `/mcp`:
  - `get_datetime` — current date/time/timezone with optional IANA tz override
  - `get_system_info` — OS, CPU, RAM/swap, GPU, system model
- [x] Tool-use loop: non-streaming probe → execute tool_calls → stream final response
- [x] `is_retry` flag prevents duplicate user message persistence

### M2 — Electron shell + chat UI ✅
**Goal:** Working desktop app with full chat UX, memory, and developer tooling.

- [x] Electron project (electron-vite 3, React 19, TypeScript 5, Vite 6)
- [x] VS Code dark theme CSS variables + Ant Design 5 dark algorithm token overrides
- [x] **Tabbed shell** — Chat · Memory · Tokenizer · Diagnostics
- [x] **3-panel chat layout:**
  - Left sidebar — conversation list with search, rename, delete; new conversation button; relative timestamps; auto-scroll; last-used conversation restored on reload
  - Main panel — message bubbles (user right/blue, assistant left), streaming cursor, copy button, retry on last user message, per-message delete
  - Right panel (collapsible) — conversation cost + token counts; provider health tags
- [x] Messages rendered as Markdown with syntax highlighting (`react-markdown` + `rehype-highlight` + github-dark theme)
- [x] Message composer: auto-growing textarea, Enter to send / Shift+Enter for newline
- [x] Settings modal:
  - **Models tab** — temperature, max tokens, context window depth
  - **System Prompt tab** — free-text; defaults to Mara persona prompt
- [x] Context Inspector drawer — live tool list fetched from `/v1/tools`, reconstructed message list with context window truncation, connection status
- [x] Diagnostic Dashboard tab — provider health panel (Azure + Ollama, 30s auto-refresh), full API tester
- [x] Auto-title: first user message (≤60 chars) patched to backend
- [x] Retry: discards last assistant turn, avoids stale closure via `historyOverride`
- [x] Settings and active conversation persisted to localStorage (Zustand `persist`)
- [x] Graceful SSE error handling — content filter hits and Azure errors surfaced inline in the message thread
- [x] **Knowledge graph memory** (`memories` table, S/P/O triples):
  - TTL decay (configurable hours), pinning, `expires_at` index
  - Vector semantic search via `memory_embeddings` vec0 table + cosine similarity
  - Fallback to LIKE keyword search when no embedding match
  - CRUD endpoints: `GET/POST /v1/memories`, `PATCH/DELETE /v1/memories/{id}`
  - Memory tab UI: pinned rows highlighted, expiry countdown, search, create/edit modal
  - Memory injected into system prompt on every chat turn
- [x] **Additional MCP tools:**
  - `get_location` — IP geolocation via ip-api.com (checks memory for user override first)
  - `get_weather` — current + 7-day forecast via Open-Meteo (no API key); °F, mph, inches
  - `store_memory`, `search_memories`, `list_memories`, `pin_memory`, `delete_memory` — all wired into TOOLS registry and chat tool-use loop
- [x] **Tokenizer tab** — Tekken v3 tokenizer (131k vocab, tiktoken-based):
  - Debounced live tokenization as you type
  - Color-coded token boxes with hover tooltip (id + raw value)
  - Special token highlighting, space/newline/tab visual markers
  - Reconstructed text panel + round-trip match indicator
  - Token details table (index, id, piece, special flag)

### M3 — Web search tool ✅
**Goal:** Assistant can look up current information via Tavily.

- [x] `tools/search.py` — Tavily search via httpx; records every call before executing
- [x] Wired into MCP server + tool-use loop
- [x] Tool result injected into context as a structured result list
- [x] "Searched: \<query\>" pill with search icon shown above assistant bubble
- [x] `GET /v1/tools` endpoint — live tool manifest derived from `TOOLS` registry; Context Inspector fetches dynamically (no hardcoded list to maintain)
- [x] Tavily free-tier quota tracking:
  - `search_calls` table + `GET /v1/search/usage` endpoint
  - Progress bar on Diagnostics tab, colour-coded at 70%/90%
  - Days-until-reset and reset date displayed
  - Portal baseline offset (click-to-edit) to reconcile with Tavily web portal count
- [x] Citation cards: search result sources (title, hostname, URL) rendered as clickable cards below the assistant reply; hover highlights border in accent colour

### M4 — Cost dashboard ✅
**Goal:** Measurable, comparable cost visibility.

- [x] Model comparison table: total spent, avg per call, token counts, provider tag — in Cost sub-tab of Diagnostics
- [x] Daily spend chart (Recharts AreaChart, 7d/30d/90d window selector)
- [x] Per-provider breakdown (provider tag per row in model table)
- [x] Cost alert: warning banner when all-time spend exceeds configurable threshold; click-to-edit "Alert at" stat card; persisted to localStorage
- [x] Export usage as CSV (model breakdown + daily rows, dated filename)

### M5 — Message reactions ✅
**Goal:** Users and Mara can react to messages with emoji; reactions feed back into Mara's context and behaviour.

#### Storage
- [x] `reactions` table: `id`, `message_id` (FK → messages), `author` (`user` | `assistant`), `emoji`, `created_at`
- [x] `GET /v1/reactions/{message_id}` — list reactions for a message
- [x] `POST /v1/reactions/{message_id}` — add a reaction `{author, emoji}`
- [x] `DELETE /v1/reactions/{reaction_id}` — remove a reaction (toggle off)

#### Context injection — ephemeral, tool-shaped
- [x] `get_recent_reactions` — called server-side before every probe; injected as a synthetic `assistant` tool_call + `tool` result pair; always fires when any messages exist (gives Mara valid message IDs to react to)
- [x] Injection payload includes message `id`, `role`, 80-char content `preview`, and existing `reactions` per message
- [x] Reactions roll out of context naturally as messages age past the window
- [x] RAG-retrieved chunks enriched with reaction summary at read time (e.g. `[reactions: user: 👍, assistant: ❤️]`) — embedding stays clean, enrichment applied on retrieval

#### Mara writes reactions (tool)
- [x] `react_to_message` MCP tool + TOOLS registry entry — args: `message_id`, `emoji`; writes `author='assistant'` row
- [x] System prompt guidance added: sparingly, a reaction alone is valid when presence is enough

#### UI
- [x] Reaction `☺` button in the message action bar (next to copy/delete), always visible when not streaming
- [x] Fixed palette of 12 emoji (👍 ❤️ 😂 😮 😢 😡 🎉 🤔 👀 🙌 🔥 ✅); click-outside closes; user reactions constrained to palette, Mara may use any emoji
- [x] Reaction row below bubble: grouped by emoji with count; user-reacted items highlighted; click to toggle off
- [x] Assistant reactions shown in reaction row (no picker); `react_to_message` tool call shown as "Reacted 🔥" pill
- [x] Reactions loaded on conversation open; optimistic add with temp ID replaced on server response
- [x] SSE `done` event carries real server-assigned `user_msg_id` and `assistant_msg_id`; frontend swaps optimistic IDs so reactions POST to valid message IDs immediately

### M6 — Google account tools ✅
**Goal:** Mara can read and write the user's calendar and tasks, and search Drive for files.

#### Scope decisions
- Calendar: full read/write (create, update, delete events)
- Tasks: full read/write (create, complete, update, delete); default list is "My Tasks" but all lists discoverable
- Drive: **read-only** — search + fetch file metadata and plain-text content preview; writing back to Drive is out of scope for this milestone

#### Auth
- [x] Google OAuth 2.0 flow — backend starts loopback listener on `localhost:8080`, returns auth URL; frontend opens via `shell.openExternal` IPC; callback exchanges code for tokens
- [x] Tokens (access + refresh) stored in `google_tokens` SQLite table (single-row, id=1)
- [x] Automatic access token refresh using stored refresh token (tokens expire after 1 hour)
- [x] Sign-out / revoke flow — calls Google revoke endpoint, clears DB row; accessible from Settings
- [x] Auth state indicator in Settings → Google tab: "Connected as user@gmail.com" or "Not connected" with Connect/Disconnect button
- [x] IPC channel: `open-external` (renderer → main → `shell.openExternal`); auth status polled via REST

#### Calendar tools
- [x] `list_calendars` — enumerate all calendars (id, name, primary flag)
- [x] `get_calendar_events` — fetch events in a date range; args: `calendar_id`, `time_min`, `time_max`, `max_results`
- [x] `create_calendar_event` — args: `calendar_id`, `summary`, `start`, `end`, `description?`, `attendees?`
- [x] `update_calendar_event` — args: `calendar_id`, `event_id`, fields to patch
- [x] `delete_calendar_event` — args: `calendar_id`, `event_id`

#### Tasks tools
- [x] `list_task_lists` — enumerate all task lists (id, title)
- [x] `get_tasks` — fetch tasks from a list; args: `task_list_id` (default `@default`), `show_completed?`
- [x] `create_task` — args: `task_list_id`, `title`, `notes?`, `due?`
- [x] `complete_task` — mark a task done; args: `task_list_id`, `task_id`
- [x] `update_task` — args: `task_list_id`, `task_id`, fields to patch (title, notes, due)
- [x] `delete_task` — args: `task_list_id`, `task_id`

#### Drive tools (read-only)
- [x] `search_drive` — full-text search across Drive; returns file id, name, mimeType, webViewLink
- [x] `get_drive_file` — fetch metadata + plain-text content preview (first 2000 chars; Docs/Sheets exported as text/csv)

#### Wiring
- [x] All 13 tools (11 + list_calendars + list_task_lists) in TOOLS registry and `execute_tool` handler
- [x] All 13 tools defined as MCP tools in `mcp_server.py`
- [x] `tools/google.py` — Google API client wrapper (`google-api-python-client` + `google-auth-oauthlib`)
- [x] Tool invocations shown inline: 📅 calendar labels, ✅ task labels, 📁 Drive labels
- [x] Google tools listed in Context Inspector via `/v1/tools` (automatic)
- [x] `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` populated in `.env` (project `local-assist-495822`)

#### Post-M6 fixes
- [x] OAuth loopback server: teardown stale server before rebinding on retry; `allow_reuse_address = True`; PKCE verifier preserved by reusing the same `Flow` object through the exchange
- [x] Token exchange moved to `run_in_executor` (was blocking the event loop); errors now logged instead of silently swallowed
- [x] SQLite thread-safety: `_LockedConn` proxy serialises all `execute`/`commit`/`rollback` calls through a `threading.Lock`; both `conn()` endpoints and `shared_connection()` (MCP) go through the proxy — eliminates `SQLITE_MISUSE` under concurrent requests
- [x] Multi-round tool loop: tool-use loop runs up to 5 rounds (was 1); allows Mara to fetch IDs in one round then act on them (update/delete) in the next
- [x] Tool descriptions: `update_calendar_event`, `delete_calendar_event`, `complete_task`, `update_task`, `delete_task` — all explicitly state "call the fetch tool first to obtain the real ID; never guess"
- [x] `list_task_lists` / `get_tasks` descriptions updated: tasks have no server-side search; Mara must fetch all lists and match by substring
- [x] All markdown links and citation card links route through `shell.openExternal` — prevents Google Docs and other URLs from taking over the Electron window
- [x] Right-panel cost/token totals now fetch cumulative `GET /v1/usage/:id` after each turn instead of displaying single-turn values from the SSE `done` event

### M7 — Event-driven notifications
**Goal:** Mara can be proactively triggered by external events and respond without user prompting.

- [ ] Define event source abstraction: polling interval, webhook listener, or filesystem watch
- [ ] Initial event sources to consider: calendar reminders, system alerts (high CPU/RAM), scheduled check-ins
- [ ] Event queue: buffer incoming events, deduplicate, throttle
- [ ] Notification surface: tray badge + toast; optionally open chat with pre-populated context
- [ ] Mara response loop: inject event as a system message, allow tool use, surface reply as notification or in thread
- [ ] User controls: per-source enable/disable, quiet hours, priority threshold

#### Notes for Claude

- Any events or loops that Mara is watching will need to end up on the Diagnostics screen so we can keep an eye on them, and possible delete the ones we don't want.

### M8 — Speech I/O
**Goal:** Voice in, voice out via Azure.

- [ ] STT: stream mic audio → Azure `gpt-4o-transcribe` → text
- [ ] TTS: assistant reply → Azure `gpt-4o-mini-tts` → audio playback
- [ ] Voice selection (alloy/echo/fable/onyx/nova/shimmer) in Settings
- [ ] IPC: `start-listening`, `stop-listening`, `speak`, `stop-speaking`
- [ ] Push-to-talk mode (hold key) and continuous mode toggle

### M9 — Vision
**Goal:** Send images, get analysis back.

- [ ] Image attach: drag-drop or file picker → base64 → multimodal message
- [ ] Screenshot capture shortcut (Electron `desktopCapturer`)
- [ ] Image displayed inline in thread

### M10 — Polish + packaging
**Goal:** Installable app.

- [ ] In-app toast notification system (copy confirmation, non-fatal errors, tool completion feedback)
- [ ] System tray icon with quick-ask popup
- [ ] Global hotkey to open/focus window
- [ ] Bundle `.venv` via electron-builder `extraResources`; validate `sqlite-vec` native extension
- [ ] electron-builder: Linux AppImage + Windows NSIS (macOS out of scope)
- [ ] Auto-update scaffold (electron-updater)

### Future Exploration
- Custom web search crawler (no Tavily dependency): direct HTTP fetch + HTML extraction; good candidates are sites with structured data or public APIs (Wikipedia, Stack Overflow). Stack Overflow's API could also support writing answers back to the community.
- GCP billing visibility: Google's Cloud Billing API exposes only account metadata and budget alerts — credit balance and amount owed are not available programmatically. Real-time spend data requires enabling **BigQuery billing export** (Console → Billing → Data export), which streams all spend into a queryable dataset with ~1-day lag. If added, this would be a `query_gcp_costs` tool backed by the BigQuery API.

---

## Project Structure

```
~/projects/local-assist/
├── src/
│   ├── renderer/                  # React UI (Vite, renderer process)
│   │   ├── components/
│   │   │   ├── ChatView.tsx             ✓  3-panel layout + send/retry/delete logic
│   │   │   ├── ChatThread.tsx           ✓  message bubbles, markdown, streaming cursor
│   │   │   ├── MessageComposer.tsx      ✓  textarea, send button
│   │   │   ├── ConversationList.tsx     ✓  search, rename, delete, active state
│   │   │   ├── RightPanel.tsx           ✓  cost + provider health
│   │   │   ├── SettingsModal.tsx        ✓  model params + system prompt
│   │   │   ├── ContextInspector.tsx     ✓  debug drawer, live tool list
│   │   │   ├── MemoryView.tsx           ✓  knowledge graph CRUD
│   │   │   ├── TokenizerView.tsx        ✓  Tekken tokenizer test UI
│   │   │   ├── CostDashboard.tsx        ✓  spend chart, model table, alert threshold, CSV export
│   │   │   └── DiagnosticDashboard.tsx  ✓  health panel + API tester + search quota + cost sub-tab
│   │   ├── styles/index.css       ✓ VS Code dark theme + Tailwind v4
│   │   ├── store.ts               ✓ Zustand 5 store + persist middleware
│   │   ├── electron.d.ts          ✓ window.electronAPI types
│   │   └── App.tsx                ✓ AntD ConfigProvider + tabbed shell
│   ├── main/
│   │   └── index.ts               ✓ Electron main + IPC + sidecar spawn + open-external handler
│   ├── preload/index.ts           ✓ contextBridge → window.electronAPI
│   ├── backend/                   # FastAPI sidecar (Python)
│   │   ├── main.py                ✓ routes, tool-use loop, MCP mount
│   │   ├── router.py              ✓ provider routing + call_with_tools
│   │   ├── mcp_server.py          ✓ FastMCP tool definitions
│   │   ├── rag.py                 ✓ sqlite-vec embed + retrieve
│   │   ├── cost.py                ✓ usage recording + reporting
│   │   ├── database.py            ✓ schema, migrations, CRUD
│   │   ├── providers/
│   │   │   ├── azure.py           ✓ streaming + tool call support
│   │   │   └── ollama.py          ✓ streaming + tool call support
│   │   └── tools/
│   │       ├── datetime_tool.py   ✓ current date/time/timezone
│   │       ├── system_info_tool.py ✓ CPU/RAM/GPU/OS snapshot
│   │       ├── location_tool.py   ✓ IP geolocation (ip-api.com)
│   │       ├── weather_tool.py    ✓ forecast (Open-Meteo)
│   │       ├── memory_tool.py     ✓ knowledge graph CRUD + vector search
│   │       ├── tokenizer_tool.py  ✓ Tekken v3 tokenizer
│   │       ├── search.py          ✓ Tavily web search + quota tracking
│   │       └── google.py          ✓ Calendar / Tasks / Drive (M6)
│   └── shared/types.ts            ✓ Conversation, Message, ModelId, etc.
├── .env
├── package.json                   ✓
├── requirements.txt               ✓
├── tsconfig.json                  ✓ project references
├── electron.vite.config.ts        ✓
└── electron-builder.config.ts     ✓
```
