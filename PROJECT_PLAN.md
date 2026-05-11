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
- [x] SQLite schema: `conversations`, `messages`, `usage`, `pricing`, `embeddings`, `reactions`, `google_tokens`, `watchers`, `settings`
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

### M7 — Event-driven notifications ✅
**Goal:** Mara can be proactively triggered by external events and respond without user prompting.

- [x] In-app toast notification system (`useToast` hook wrapping Ant Design `App.useApp()`; `<AntApp>` wrapper in App.tsx; copy confirmation, error/warning toasts wired into ChatView and ChatThread)
- [x] Event source abstraction: `Watcher` dataclass with pluggable `_poll_fn`, configurable `interval_seconds`, `enabled` flag, `last_run` / `last_error` tracking; `WatcherRegistry` singleton with asyncio poll tasks and shared `Queue[EventItem]`
- [x] Initial event sources:
  - **Calendar reminders** — polls Google Calendar every 2 min for events starting within 30 min; session-level dedup via `_announced` set
  - **System resource alerts** — checks CPU ≥ 90% and RAM ≥ 90% every 60 s; 5-minute per-resource cooldown (via `psutil`)
  - **Scheduled check-ins** — fires every 4 hours; `enabled=False` by default (opt-in)
- [x] Event queue: `asyncio.Queue` shared across all watchers; events emitted with `EventItem` (id, watcher_id, title, body, fired_at, optional conversation_id)
- [x] Response loop: queue drain → SSE push to all `/v1/notifications` clients → `NotificationListener` (frontend) calls `POST /v1/events/handle` with active conversation context → Mara generates reply → reply persisted to the active conversation (or a newly created one if none is open)
- [x] `POST /v1/events/handle` — receives event payload + active `conversation_id`; loads conversation history; injects event as a synthetic user turn (invisible to the user; not persisted); generates and persists only the assistant reply
- [x] Notification surface: SSE stream at `GET /v1/notifications`; `NotificationListener` component in App.tsx subscribes; on event fires an Ant Design `notification.info` toast (`bottomRight`, 10 s) and appends Mara's reply to the active conversation
- [x] REST API:
  - `GET /v1/watchers` — list all registered watchers
  - `PATCH /v1/watchers/{id}` — toggle `enabled`, change `interval_seconds` (persisted to `settings` table), or update alarm enabled state
  - `DELETE /v1/watchers/{id}` — remove watcher and cancel its asyncio task
- [x] Diagnostics **Watchers tab** — lists all active watchers; built-in watchers show an inline interval editor (number + unit dropdown, saves on blur/Enter); alarm watchers show fire time; enable/disable switch; delete with confirmation; 10-second auto-refresh
- [x] **`set_reminder` tool** (MCP + TOOLS registry) — Mara can create one-shot alarm watchers at a user-specified time; server validates `fire_at` is in the future (rejects past dates with an error directing Mara to call `get_datetime` first); tool available in both MCP server and chat tool-use loop
- [x] Alarm watcher persistence: `watchers` table in SQLite; pending alarms restored on restart; self-deleted from DB when fired or manually removed via delete hook
- [x] `tools_used` column in `messages` table — tool invocation metadata (tool name, query, results, weather, reaction) persisted as JSON; deserialized and returned with `GET /v1/conversations/{id}` so tool-call indicators survive conversation reload
- [x] Watcher poll intervals persisted in `settings` key/value table (`watcher_interval.<source_type>`); loaded at startup so interval changes survive restarts
- [x] Backend logging to disk: uvicorn output tee'd to `~/.config/local-assist/logs/backend.log` in dev mode; timestamped write stream in production (`spawnBackend`)
- [x] **Spend threshold watcher** (`cost_watcher.py`) — polls every 5 min; fires when all-time cost crosses the configured alert threshold (re-fires at each additional multiple); threshold synced from frontend to `settings.cost_alert_threshold` via `PUT /v1/settings/cost-alert` on every change in CostDashboard
- [x] **Quiet hours** — `GET/PUT /v1/quiet-hours` backed by `settings` table; default 9 PM–7 AM, enabled by default; response loop checks before pushing SSE events and drops silently during the window; configurable from the **Watchers tab** (toggle + time-range pickers above the watcher list)

### M8 — Speech I/O + Procedural Sound ✅
**Goal:** Voice in, voice out via Azure and local models; Mara can generate and play sounds on demand.

#### Voice I/O
- [x] Azure TTS backend: `POST /v1/audio/speech` → MP3 bytes via `gpt-4o-mini-tts`
- [x] Azure STT backend: `POST /v1/audio/transcriptions` → transcript via `gpt-4o-transcribe`
- [x] `GET /v1/audio/voices` — list available TTS voices (provider-aware)
- [x] CSP: `media-src 'self' blob:` added to allow `URL.createObjectURL` audio playback
- [x] Voice selection in Settings → Voice tab; persisted to store; shared by Speak button, Sound Lab, and voice input
- [x] TTS opt-in speak: speaker icon on each assistant bubble → LLM rewrites markdown for speech → TTS → plays in hidden audio element; clicking again stops; accent colour while playing; `POST /v1/audio/speak` endpoint handles LLM rewrite + synthesis in one call
- [x] Voice input in chat composer: mic button → MediaRecorder → webm blob → STT → appends transcript to textarea; red/danger while recording, spinner while transcribing

#### Local speech (in-process, no separate servers)
- [x] `src/backend/providers/local_speech.py` — kokoro `KPipeline` (TTS) + faster-whisper `WhisperModel` (STT); both load lazily on first call and are kept as module-level singletons
- [x] Kokoro voices: af_heart, af_bella, af_nicole, af_sarah, af_sky, am_adam, am_michael, bf_emma, bf_isabella, bm_george, bm_lewis (American + British English; pipeline selected by voice prefix)
- [x] faster-whisper model sizes: tiny · tiny.en · base · base.en · small · small.en · medium · medium.en · large-v1 · large-v2 · large-v3; `int8` quantisation on CPU
- [x] Audio pipeline: PCM → MP3 via `lameenc` (WAV fallback); webm STT input decoded via `soundfile` → ffmpeg subprocess fallback → resampled to 16 kHz
- [x] `GET/PUT /v1/audio/provider` — read/set active provider (`azure` | `local`); persisted to settings table
- [x] `GET/PUT /v1/audio/stt-model` — read/set Whisper model size; `POST /v1/audio/stt-model/load` — eagerly load (triggers HuggingFace download if needed)
- [x] Persisted Whisper model size restored from settings DB on backend startup
- [x] `speechProvider` in Zustand store — shared across all components; DiagnosticDashboard reads from backend on mount and writes to store on toggle; Sound Lab reads from store
- [x] Diagnostics → Status tab: Voice (TTS/STT) section with provider toggle, Kokoro TTS + Whisper STT health badges, STT model dropdown, Download/Load button + "in memory" tag
- [x] `/v1/health` extended with `local_tts` and `local_stt` boolean fields
- [x] Sound Lab TTS panel adapts voice list and speed range (Azure: 0.25–4×; Kokoro: 0.5–2×) reactively when provider changes; shows `Kokoro` or `Azure` tag

#### Procedural sound engine
- [x] bfxr engine in TypeScript (`src/renderer/bfxr.ts`) — single-oscillator synth (square / sawtooth / sine / triangle / noise / breaker), ADSR envelope, frequency slide + delta, vibrato, arpeggio, duty sweep, phaser/flanger, LP/HP filters; renders to Float32Array via Web Audio API at 44100 Hz; no dependencies
- [x] Shared `AudioContext` singleton (`getSharedAudioContext()`); `ctx.resume()` called before playback; `pointerdown` primer in ChatView ensures context is unlocked before tool-triggered sounds
- [x] Named preset library (`src/renderer/soundPresets.ts`): `coin`, `laser`, `powerup`, `blip`, `explosion`, `dial-up`, `startup`
- [x] `play_sound` tool — Mara calls with preset name or partial param overrides; partial params merged with `DEFAULT_PARAMS` before playback; SSE `done` event triggers `bfxrPlay()` in renderer; shown as 🔊 pill in message thread
- [x] `search_sounds` tool — semantic search via sqlite-vec cosine similarity over `sound_embeddings` table; LIKE fallback; returns preset names + params
- [x] Sounds seeded at startup (`seed_sounds()`): builtin presets into `sounds` + `sound_embeddings` tables; Azure embeddings fetched on first run
- [x] Sound replay widget below assistant bubbles that used `play_sound` — click to re-play or stop; shows SoundTwoTone while playing
- [x] **Sound Lab tab** — fully implemented:
  - TTS panel: textarea, voice picker, speed slider (range adapts to provider), synthesize + playback; provider badge
  - STT panel: mic recording → transcript display
  - Sound Library: preset browser with descriptions + wave type tag + click-to-preview; collapsible parameter editor per preset (bfxr-style sliders for all params, wave type grid buttons); dirty indicator + reset button; edits immediately retrigger playback

#### SVG rendering
- [x] SVG code blocks (` ```svg ` or ` ```xml ` fences whose content starts with `<svg`) render an inline collapsible preview above the syntax-highlighted code
- [x] Preview extracted by recursively walking the hast tree after `rehype-highlight` (text is fragmented into nested highlight spans; shallow `.value` read was insufficient)
- [x] Rendered as `<img src="data:image/svg+xml;...">` — sandboxed, no script execution
- [x] CSP `img-src 'self' blob: data:` added to allow inline `data:` image URIs

### Post-M8 — Vertex AI provider ✅
**Goal:** Add Vertex AI (GCP) as a second cloud provider, filling the gap when Azure is degraded.

- [x] `src/backend/providers/vertex.py` — Mistral Large 3 via Vertex Model Garden OpenAI-compatible endpoint; Google ADC auth; streaming + `_non_streaming_fallback`; `call_with_tools`; `health_check`
- [x] `router.py` rewritten — Azure → Vertex → Ollama fallback chain; `_pick_cloud_provider()` probes both cloud providers concurrently via `asyncio.gather`; manual pin via `set_provider_setting_fn` callback (avoids circular import)
- [x] `GET/PUT /v1/chat/provider` — read/set preferred provider (`auto` | `azure` | `vertex` | `ollama`); persisted to settings DB
- [x] `HealthStatus` extended with `vertex: boolean` and `preferred_provider` fields; `GET /v1/health` probes all 5 endpoints
- [x] Diagnostics → Status: Vertex AI health badge; Preferred provider selector (Auto/Azure/Vertex/Ollama)
- [x] `.env` — `GCP_PROJECT` + `VERTEX_REGION` optional vars; auth via `gcloud auth application-default login`

### M9 — Vision
**Goal:** Send images, get analysis back.

- [ ] Image attach: drag-drop or file picker → base64 → multimodal message
- [ ] Screenshot capture shortcut (Electron `desktopCapturer`)
- [ ] Image displayed inline in thread

### M10 — Polish + packaging
**Goal:** Installable app.

- [ ] System tray icon with quick-ask popup
- [ ] Global hotkey to open/focus window
- [ ] Bundle `.venv` via electron-builder `extraResources`; validate `sqlite-vec` native extension
- [ ] electron-builder: Linux AppImage + Windows NSIS (macOS out of scope)
- [ ] Auto-update scaffold (electron-updater)

### Future Exploration
- Custom web search crawler (no Tavily dependency): direct HTTP fetch + HTML extraction; good candidates are sites with structured data or public APIs (Wikipedia, Stack Overflow). Stack Overflow's API could also support writing answers back to the community.
- GCP billing visibility: Google's Cloud Billing API exposes only account metadata and budget alerts — credit balance and amount owed are not available programmatically. Real-time spend data requires enabling **BigQuery billing export** (Console → Billing → Data export), which streams all spend into a queryable dataset with ~1-day lag. If added, this would be a `query_gcp_costs` tool backed by the BigQuery API.
- **Deferred tool schemas**: as the tool count grows, sending all 26+ full tool definitions on every request wastes context tokens and increases selection error risk. Explore sending only tool names + one-line descriptions by default, with a `get_tool_schema(name)` meta-tool Mara can call to fetch the full parameter definition before invoking an unfamiliar tool. Net effect: lower per-request token cost, cleaner active context. Open question is whether Mistral Large 3 reliably recognizes when it needs to fetch a schema vs. guessing — worth benchmarking once the tool count crosses ~30.
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
│   │   │   ├── SoundLabView.tsx         ✓  TTS/STT panels + bfxr preset browser + param editor
│   │   │   ├── CostDashboard.tsx        ✓  spend chart, model table, alert threshold, CSV export
│   │   │   └── DiagnosticDashboard.tsx  ✓  health, API tester, search quota, voice servers, cost
│   │   ├── styles/index.css       ✓ VS Code dark theme + Tailwind v4
│   │   ├── store.ts               ✓ Zustand 5 store + persist middleware
│   │   ├── bfxr.ts                ✓ procedural sound engine (PCM synth + Web Audio API)
│   │   ├── soundPresets.ts        ✓ 7 named bfxr presets
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
│   │   │   ├── azure.py           ✓ streaming + tool call support + 500 fallback
│   │   │   ├── vertex.py          ✓ Vertex AI (GCP) streaming + tool call support + ADC auth
│   │   │   ├── ollama.py          ✓ streaming + tool call support
│   │   │   ├── speech.py          ✓ Azure TTS (gpt-4o-mini-tts) + STT (gpt-4o-transcribe)
│   │   │   └── local_speech.py    ✓ in-process Kokoro TTS + faster-whisper STT
│   │   ├── events/                # M7 event-driven notification system
│   │   │   ├── watcher.py         ✓ WatcherRegistry, Watcher, EventItem; one-shot + interval modes
│   │   │   ├── response_loop.py   ✓ queue drain → SSE push
│   │   │   └── sources/
│   │   │       ├── calendar_watcher.py  ✓ Google Calendar reminders (30-min lookahead)
│   │   │       ├── system_watcher.py    ✓ CPU/RAM threshold alerts (psutil)
│   │   │       ├── schedule_watcher.py  ✓ periodic check-ins (4h, opt-in)
│   │   │       ├── alarm_watcher.py     ✓ one-shot datetime alarms (set_reminder tool)
│   │   │       └── cost_watcher.py      ✓ spend threshold alerts (synced from CostDashboard)
│   │   └── tools/
│   │       ├── datetime_tool.py   ✓ current date/time/timezone
│   │       ├── system_info_tool.py ✓ CPU/RAM/GPU/OS snapshot
│   │       ├── location_tool.py   ✓ IP geolocation (ip-api.com)
│   │       ├── weather_tool.py    ✓ forecast (Open-Meteo)
│   │       ├── memory_tool.py     ✓ knowledge graph CRUD + vector search
│   │       ├── tokenizer_tool.py  ✓ Tekken v3 tokenizer
│   │       ├── search.py          ✓ Tavily web search + quota tracking
│   │       ├── google.py          ✓ Calendar / Tasks / Drive (M6)
│   │       └── sound_tool.py      ✓ play_sound + search_sounds + sqlite-vec embeddings
│   └── shared/types.ts            ✓ Conversation, Message, ModelId, etc.
├── .env
├── package.json                   ✓
├── requirements.txt               ✓
├── tsconfig.json                  ✓ project references
├── electron.vite.config.ts        ✓
└── electron-builder.config.ts     ✓
```
