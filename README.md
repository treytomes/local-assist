# Local Assist

A local-first AI desktop assistant built with Electron, React, and a FastAPI Python sidecar. Powered by **Mistral Large 3** via Azure AI, with automatic fallback to a local Ollama instance when offline.

---

## Features

### Chat
- Persistent conversation history stored in SQLite
- Streaming responses rendered as **Markdown with syntax highlighting**
- Copy, retry, or delete any message in the thread
- Auto-generated conversation titles from the first message
- Last-used conversation restored on relaunch
- Collapsible right panel showing per-conversation token usage and cost

### AI Tools (MCP)
The backend doubles as an MCP server. Mara can call tools mid-conversation:
- **get_datetime** — current date, time, and timezone (optional IANA tz override)
- **get_system_info** — OS, CPU model/usage, RAM/swap, GPU details, system model name
- **get_location** — IP geolocation; respects a user-stored location override in memory
- **get_weather** — current conditions + 7-day forecast via Open-Meteo; renders an inline weather card in the thread
- **web_search** — web search via Tavily; results shown as citation cards below the assistant bubble
- **store_memory / search_memories / list_memories / pin_memory / delete_memory** — knowledge graph operations
- **list_calendars / get_calendar_events / create_calendar_event / update_calendar_event / delete_calendar_event** — Google Calendar full read/write (requires OAuth)
- **list_task_lists / get_tasks / create_task / complete_task / update_task / delete_task** — Google Tasks across all lists (requires OAuth)
- **search_drive / get_drive_file** — Google Drive read-only search and plain-text file preview (requires OAuth)

The available tool list is served dynamically from `GET /v1/tools` — the Context Inspector always reflects the live set without any hardcoded frontend mirror.

### Memory
Two complementary memory systems:

**RAG** — past assistant replies are embedded via `sqlite-vec` and retrieved as context at the start of each new conversation turn, including from previous conversations.

**Knowledge graph** — structured S/P/O triples (e.g. `user → prefers → dark mode`):
- TTL decay: facts expire after a configurable number of hours
- Pinning: important facts can be marked permanent
- Vector semantic search with cosine similarity; keyword fallback
- Full CRUD via the **Memory tab** in the UI

### Tokenizer
A built-in **Tekken v3** tokenizer test tab (the actual Mistral Large 3 tokenizer, 131k vocab):
- Live tokenization as you type (debounced)
- Color-coded token boxes with hover tooltip showing ID and raw value
- Special token highlighting, visual markers for spaces/newlines/tabs
- Reconstructed text panel with round-trip match indicator
- Full token details table

### Settings
- Inference parameters: temperature, max tokens, context window depth
- Global system prompt (defaults to the Mara persona)
- All settings persisted to localStorage across sessions

### Developer Tools
- **Context Inspector** — shows the exact message list sent to the model on the next turn, with context window truncation applied, plus live tool list and connection status
- **Diagnostic Dashboard** — provider health (Azure + Ollama, 30s auto-refresh), Tavily search quota progress bar with portal baseline offset, full API tester for all backend endpoints

### Message Reactions
- React to any message with emoji from a fixed 12-emoji palette (👍 ❤️ 😂 😮 😢 😡 🎉 🤔 👀 🙌 🔥 ✅)
- Mara can react to messages too via the `react_to_message` tool, using any emoji she chooses
- Reactions are grouped below each bubble with counts; click to toggle your own reaction off
- Reactions are injected into Mara's context before every turn so she can see and respond to them
- RAG-retrieved chunks include reaction summaries so past emotional signals carry forward

### Cost Tracking
- Token usage and USD cost recorded per message; right panel shows **cumulative** conversation totals
- Per-conversation cost summary in the right panel
- **Cost Dashboard** (Diagnostics tab): daily spend chart (7d/30d/90d), per-model breakdown table, spend alert threshold, CSV export

---

## Tech Stack

| Layer | Technology |
|---|---|
| Desktop shell | Electron 33 + electron-vite 3 |
| Frontend | React 19 + TypeScript + Vite 6 |
| UI | Ant Design 5 + Tailwind CSS 4 (VS Code dark theme) |
| State | Zustand 5 with persist middleware |
| Backend | FastAPI (Python 3.11+) sidecar |
| Database | SQLite via better-sqlite3 + sqlite-vec for embeddings |
| Tool protocol | MCP (`mcp[cli]`) mounted as ASGI sub-app at `/mcp` |
| Primary AI | Azure AI — `Mistral-Large-3` |
| Fallback AI | Ollama (`gemma3:1b` auto-pulled if not present) |
| Tokenizer | `mistral-common` Tekken v3 (131k vocab, tiktoken) |

---

## Prerequisites

- Node.js 20+
- Python 3.11+
- An Azure AI Foundry project with `Mistral-Large-3` deployed (or Ollama running locally)

## Setup

```bash
# Install Node dependencies
npm install

# Create and activate a Python virtual environment
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

# Install Python dependencies
pip install -r requirements.txt

# Download the Tekken tokenizer file (one-time)
python -c "
from huggingface_hub import hf_hub_download
hf_hub_download('mistralai/Mistral-Nemo-Instruct-2407', 'tekken.json',
                local_dir='~/.local/share/mistral-tokenizers')
"

# Copy and fill in environment variables
cp .env.example .env
# Edit .env with your Azure credentials
```

### Required environment variables

```
AZURE_INFERENCE_ENDPOINT=https://<your-resource>.cognitiveservices.azure.com/
AZURE_API_KEY=<your-key>
```

### Optional

```
TAVILY_API_KEY=<your-key>           # enables web search
GOOGLE_CLIENT_ID=<your-client-id>   # enables Calendar, Tasks, Drive
GOOGLE_CLIENT_SECRET=<your-secret>
```

#### Google OAuth setup

1. Open [Google Cloud Console](https://console.cloud.google.com/apis/credentials) and create a project.
2. Enable the **Google Calendar API**, **Tasks API**, and **Google Drive API**.
3. Create an **OAuth 2.0 Client ID** (Application type: **Web application**).
4. Add `http://localhost:8080/oauth2callback` as an authorised redirect URI.
5. Copy the client ID and secret into `.env`.
6. In Settings → Google tab, click **Connect** to complete the OAuth flow.

## Running

```bash
npm run dev
```

This starts the Electron app, the Vite dev server, and the FastAPI sidecar together. The backend is available at `http://127.0.0.1:8000`.

> **Linux note:** If you see `ENOSPC: System limit for number of file watchers reached`, run:
> `echo fs.inotify.max_user_watches=524288 | sudo tee -a /etc/sysctl.conf && sudo sysctl -p`

## Testing

```bash
./test.sh                  # unit tests only
./test.sh --integration    # unit + integration (requires running backend)
./test.sh --azure          # full suite including live Azure calls
```

---

## Project Structure

```
src/
├── renderer/          # React UI (Electron renderer process)
│   ├── components/    # ChatView, ChatThread, MemoryView, TokenizerView, ...
│   ├── store.ts       # Zustand store + Mara system prompt
│   └── styles/        # CSS variables + Tailwind
├── main/              # Electron main process + IPC
├── preload/           # contextBridge → window.electronAPI
└── backend/           # FastAPI sidecar
    ├── main.py        # Routes + tool-use loop
    ├── mcp_server.py  # MCP tool definitions
    ├── providers/     # Azure + Ollama adapters
    └── tools/         # datetime, system_info, location, weather, memory, tokenizer
```

---

## Roadmap

- **M7** — Event-driven notifications: Mara proactively responds to calendar, system, and scheduled events; event sources visible and manageable in Diagnostics
- **M8** — Voice I/O: STT via `gpt-4o-transcribe`, TTS via `gpt-4o-mini-tts`
- **M9** — Vision: image attach and screenshot capture
- **M10** — Polish + packaging: toast notifications, system tray, AppImage / NSIS + auto-update
