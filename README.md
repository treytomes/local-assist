# Local Assist

A local-first AI desktop assistant built with Electron, React, and a FastAPI Python sidecar. Connects to Azure AI (GPT and Mistral models) with automatic fallback to a local Ollama instance when offline.

---

## Features

### Chat
- Persistent conversation history stored in SQLite
- Switch between `gpt-5.3-chat` and `Mistral-Large-3` per conversation
- Streaming responses with live token rendering
- Retry last message or delete any message from the thread
- Auto-generated conversation titles from the first message
- Last-used conversation restored on relaunch

### AI Tools (MCP)
The backend doubles as an MCP server. Mara can call tools mid-conversation:
- **get_datetime** — current date, time, and timezone (optional IANA tz override)
- **get_system_info** — OS, CPU model/usage, RAM/swap, GPU details, system model name

### Memory
- Cross-conversation RAG via `sqlite-vec`: past assistant responses are embedded and retrieved as context at the start of new conversations

### Settings
- Per-model inference parameters: temperature, max tokens, context window depth
- Global system prompt (defaults to the Mara persona)
- All settings persisted to localStorage across sessions

### Diagnostics
- **Context Inspector** — shows the exact message list that will be sent to the model on the next turn, with context window truncation applied, plus available tools and live connection status
- **Diagnostic Dashboard** — provider health (Azure + Ollama), full API tester for all backend endpoints

### Cost Tracking
- Token usage and USD cost recorded per message
- Per-conversation cost summary in the right panel
- Daily and per-model cost comparison via `/v1/usage`
- Pricing table editable at runtime via `/v1/pricing`

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
| Tool protocol | MCP (`mcp[cli]`) mounted as ASGI sub-app |
| Primary AI | Azure AI Inference — `gpt-5.3-chat`, `Mistral-Large-3` |
| Fallback AI | Ollama (`gemma3:1b` auto-pulled if not present) |

---

## Prerequisites

- Node.js 20+
- Python 3.11+
- An Azure AI Foundry project with `gpt-5.3-chat` and `Mistral-Large-3` deployed (or Ollama running locally)

## Setup

```bash
# Install Node dependencies
npm install

# Create and activate a Python virtual environment
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

# Install Python dependencies
pip install -r requirements.txt

# Copy and fill in environment variables
cp .env.example .env
# Edit .env with your Azure credentials
```

### Required environment variables

```
AZURE_INFERENCE_ENDPOINT=https://<your-resource>.cognitiveservices.azure.com/
AZURE_API_KEY=<your-key>
AZURE_OPENAI_ENDPOINT=https://<your-resource>.openai.azure.com/openai/v1
```

## Running

```bash
npm run dev
```

This starts the Electron app, the Vite dev server, and the FastAPI sidecar together. The backend is available at `http://127.0.0.1:8000`.

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
│   ├── components/    # ChatView, ChatThread, ConversationList, ...
│   ├── store.ts       # Zustand store
│   └── styles/        # CSS variables + Tailwind
├── main/              # Electron main process
├── preload/           # contextBridge IPC surface
└── backend/           # FastAPI sidecar
    ├── main.py        # Routes + tool-use loop
    ├── mcp_server.py  # MCP tool definitions
    ├── providers/     # Azure + Ollama adapters
    └── tools/         # datetime, system_info, (search, google planned)
```

---

## Roadmap

- **M3** — Voice I/O: STT via `gpt-4o-transcribe`, TTS via `gpt-4o-mini-tts`
- **M4** — Vision: image attach and screenshot capture
- **M5** — Web search via Tavily
- **M6** — Google account tools (Calendar, Tasks, Drive)
- **M7** — Cost dashboard with charts and spend alerts
- **M8** — Packaging: AppImage / NSIS / DMG + auto-update
