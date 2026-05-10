import asyncio
import logging
import sqlite3
import uuid
import os
import threading
from contextlib import asynccontextmanager
from typing import Any, Literal

log = logging.getLogger(__name__)

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

load_dotenv()

from .database import get_connection, init_db, set_shared_connection
from .cost import (
    seed_pricing, record_usage, get_conversation_cost, get_daily_costs,
    get_model_comparison, upsert_pricing, get_pricing, list_pricing,
)
from . import router as provider_router
from .rag import embed_conversation, embed_message, retrieve_context
from . import database as db
from .database import save_watcher as _db_save_watcher, delete_watcher_row as _db_delete_watcher, load_pending_watchers as _db_load_watchers, get_setting as _db_get_setting, set_setting as _db_set_setting
from .mcp_server import mcp
from .tools.datetime_tool import get_datetime as tool_get_datetime
from .tools.system_info_tool import get_system_info as tool_get_system_info
from .tools.location_tool import get_location as tool_get_location
from .tools.weather_tool import get_weather as tool_get_weather
from .tools.memory_tool import (
    store_memory as _store_memory,
    embed_memory as _embed_memory,
    search_memories as _search_memories,
    list_memories as _list_memories,
    set_pinned as _set_pinned,
    delete_memory as _delete_memory,
    get_all_as_text as _memories_as_text,
)
from .tools.search import web_search as _web_search, get_usage as _search_get_usage
from .events.watcher import WatcherRegistry, set_registry
from .events.response_loop import run_response_loop, add_sse_client, remove_sse_client
from .events.sources.calendar_watcher import make_calendar_watcher
from .events.sources.system_watcher import make_system_watcher
from .events.sources.schedule_watcher import make_schedule_watcher
from .events.sources.alarm_watcher import make_alarm_watcher
from .events.sources.cost_watcher import make_cost_watcher
from .tools.google import (
    auth_status as _google_auth_status,
    start_oauth_flow as _google_start_oauth,
    revoke_tokens as _google_revoke,
    list_calendars as _list_calendars,
    get_calendar_events as _get_calendar_events,
    create_calendar_event as _create_calendar_event,
    update_calendar_event as _update_calendar_event,
    delete_calendar_event as _delete_calendar_event,
    list_task_lists as _list_task_lists,
    get_tasks as _get_tasks,
    create_task as _create_task,
    complete_task as _complete_task,
    update_task as _update_task,
    delete_task as _delete_task,
    search_drive as _search_drive,
    get_drive_file as _get_drive_file,
)

CONTEXT_WINDOW = 20  # default rolling message depth sent to model


# --- App lifecycle ---

_conn = None
_db_lock = threading.Lock()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _conn
    raw = get_connection()
    init_db(raw)
    seed_pricing(raw)
    _conn = _LockedConn(raw, _db_lock)
    set_shared_connection(_conn)

    # Event watcher infrastructure
    def _watcher_interval(source_type: str, default: int) -> int:
        v = _db_get_setting(_conn, f"watcher_interval.{source_type}")
        try:
            return int(v) if v is not None else default
        except ValueError:
            return default

    registry = WatcherRegistry()
    cw = make_calendar_watcher(); cw.interval_seconds = _watcher_interval("calendar", cw.interval_seconds)
    sw = make_system_watcher();   sw.interval_seconds = _watcher_interval("system",   sw.interval_seconds)
    scw = make_schedule_watcher(); scw.interval_seconds = _watcher_interval("schedule", scw.interval_seconds)
    cow = make_cost_watcher();    cow.interval_seconds = _watcher_interval("cost",     cow.interval_seconds)
    registry.register(cw)
    registry.register(sw)
    registry.register(scw)
    registry.register(cow)

    # Delete hook: remove the DB row whenever an alarm watcher is deleted (fired or manual)
    def _on_watcher_delete(watcher_id: str) -> None:
        try:
            with db.transaction(_conn):
                _db_delete_watcher(_conn, watcher_id)
        except Exception:
            pass

    registry.add_delete_hook(_on_watcher_delete)

    # Restore persisted alarms that haven't fired yet
    for row in _db_load_watchers(_conn):
        w = make_alarm_watcher(row["description"], row["fire_at"], watcher_id=row["id"])
        w.enabled = bool(row["enabled"])
        registry.register(w)
        registry._start_watcher(w)

    set_registry(registry)
    registry.start_all()

    _response_loop_task = asyncio.create_task(run_response_loop(registry))

    yield

    _response_loop_task.cancel()
    if _conn:
        _conn.close()


app = FastAPI(title="local-assist backend", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount MCP server — streamable HTTP transport at /mcp
app.mount("/mcp", mcp.streamable_http_app())

# --- Tool registry (used by chat tool-use loop) ---

# OpenAI-format tool definitions sent to the model
TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "get_datetime",
            "description": "Get the current date, time, and timezone. Use this whenever the user asks about the current time, date, day, or timezone.",
            "parameters": {
                "type": "object",
                "properties": {
                    "timezone": {
                        "type": "string",
                        "description": "Optional IANA timezone name (e.g. 'America/Chicago'). Omit to use system local time.",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_system_info",
            "description": (
                "Returns a snapshot of the host machine's hardware and OS state: "
                "OS version, CPU model and core count, current CPU usage per core, "
                "RAM and swap usage, GPU details, and system model name if available. "
                "Use this when asked about the machine's specs, performance, memory, or hardware."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_location",
            "description": (
                "Returns the current location (city, region, country, lat/lon, timezone) via IP geolocation. "
                "Checks memory for a user-configured override first. "
                "Use this when the user asks where they are, or as a prerequisite for get_weather."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": (
                "Returns current weather conditions and a 7-day forecast using Open-Meteo. "
                "Resolves location automatically if lat/lon are omitted. "
                "Temperatures in °F, wind in mph, precipitation in inches."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "lat": {"type": "number", "description": "Latitude. Omit to auto-detect from location."},
                    "lon": {"type": "number", "description": "Longitude. Omit to auto-detect from location."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "store_memory",
            "description": (
                "Store a fact as a subject/predicate/object triple. Overwrites any existing memory with "
                "the same subject+predicate pair. By default facts decay after 24 hours — set pinned=true "
                "for facts that should persist indefinitely (e.g. the user's name, core preferences). "
                "Use ttl_hours to control decay: shorter for ephemeral context, longer for ongoing projects. "
                "Write the object as a full sentence when context matters — include the why and the texture, "
                "not just the bare fact. 'dislikes mornings, finds them disorienting — prefers to ease in "
                "slowly before anything demanding' is more useful than 'hates mornings'. "
                "Examples: subject='user' predicate='prefers' object='bullet-point answers, finds prose responses slow to scan' pinned=true; "
                "subject='session' predicate='focus' object='debugging the auth flow — started after noticing 401s in prod logs' ttl_hours=4."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "subject":   {"type": "string", "description": "Entity the fact is about (e.g. 'user', 'project', 'session')."},
                    "predicate": {"type": "string", "description": "Relationship or property (e.g. 'prefers', 'is working on', 'name')."},
                    "object":    {"type": "string", "description": "Value of the fact."},
                    "ttl_hours": {"type": "number", "description": "Hours until this memory expires. Default 24. Ignored when pinned=true."},
                    "pinned":    {"type": "boolean", "description": "If true, this memory never expires. Use for permanent facts like the user's name or strong preferences."},
                },
                "required": ["subject", "predicate", "object"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_memories",
            "description": "Search stored memories by keyword. Matches against subject, predicate, and object fields.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Keyword or phrase to search for."},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_memories",
            "description": "Return all stored memories. Use when you want a full picture of what you know.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_memory",
            "description": "Delete a stored memory by its ID. Use when a fact is no longer true or the user asks you to forget something.",
            "parameters": {
                "type": "object",
                "properties": {
                    "memory_id": {"type": "string", "description": "The ID of the memory to delete."},
                },
                "required": ["memory_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "pin_memory",
            "description": "Pin an existing memory so it never expires, or unpin it. Use pin=true when you learn something the user would expect you to remember permanently (name, strong preference, standing context). Use pin=false to demote a fact back to TTL-based expiry.",
            "parameters": {
                "type": "object",
                "properties": {
                    "memory_id": {"type": "string", "description": "The ID of the memory to pin or unpin."},
                    "pinned":    {"type": "boolean", "description": "True to pin (never expires), false to unpin."},
                },
                "required": ["memory_id", "pinned"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "Search the web for current information using Tavily. Use this when the user asks about "
                "recent events, live data, or anything your training data may not cover. "
                "Returns a list of relevant results with title, URL, and a content snippet."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query."},
                    "max_results": {"type": "integer", "description": "Number of results to return (1–10, default 5)."},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "react_to_message",
            "description": (
                "Add an emoji reaction to a message. Use this when something in the conversation genuinely "
                "resonates — a good idea, something funny, something worth acknowledging. Use sparingly and "
                "naturally. A reaction alone (no text) is a valid response when presence is enough — "
                "when words would diminish rather than add. Trust the moment."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "message_id": {"type": "string", "description": "The ID of the message to react to. Must be an 'id' value from the get_recent_reactions context."},
                    "emoji": {"type": "string", "description": "A single emoji character."},
                },
                "required": ["message_id", "emoji"],
            },
        },
    },
    # --- Reminders ---
    {
        "type": "function",
        "function": {
            "name": "set_reminder",
            "description": (
                "Set a one-shot reminder that will fire at a specific date and time. "
                "Mara will proactively surface the reminder message in the active conversation at the scheduled time. "
                "Always call get_datetime first to know the current time so you can calculate the correct fire_at. "
                "Use ISO 8601 format for fire_at (e.g. '2026-05-10T07:45:00'). "
                "Reminders are in-memory only and are lost if the app restarts before they fire."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "The reminder message to surface when the alarm fires.",
                    },
                    "fire_at": {
                        "type": "string",
                        "description": "ISO 8601 datetime when the reminder should fire (e.g. '2026-05-10T07:45:00').",
                    },
                },
                "required": ["message", "fire_at"],
            },
        },
    },
    # --- Google Calendar ---
    {"type": "function", "function": {
        "name": "list_calendars",
        "description": "List all Google Calendars for the connected account. Call this first to get calendar IDs before fetching events.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    }},
    {"type": "function", "function": {
        "name": "get_calendar_events",
        "description": "Fetch events from a Google Calendar within a date range.",
        "parameters": {"type": "object", "properties": {
            "calendar_id": {"type": "string", "description": "Calendar ID from list_calendars, or 'primary'."},
            "time_min": {"type": "string", "description": "RFC 3339 start datetime (default: now)."},
            "time_max": {"type": "string", "description": "RFC 3339 end datetime (optional)."},
            "max_results": {"type": "integer", "description": "Max events to return (default 10)."},
        }, "required": []},
    }},
    {"type": "function", "function": {
        "name": "create_calendar_event",
        "description": "Create a new event on a Google Calendar.",
        "parameters": {"type": "object", "properties": {
            "summary": {"type": "string", "description": "Event title."},
            "start": {"type": "string", "description": "RFC 3339 start datetime."},
            "end": {"type": "string", "description": "RFC 3339 end datetime."},
            "calendar_id": {"type": "string", "description": "Calendar ID (default 'primary')."},
            "description": {"type": "string", "description": "Event description (optional)."},
            "attendees": {"type": "array", "items": {"type": "string"}, "description": "List of attendee email addresses (optional)."},
        }, "required": ["summary", "start", "end"]},
    }},
    {"type": "function", "function": {
        "name": "update_calendar_event",
        "description": "Update fields on an existing Google Calendar event. You must call get_calendar_events first to obtain the real event_id — never guess or invent one.",
        "parameters": {"type": "object", "properties": {
            "event_id": {"type": "string", "description": "Event ID from get_calendar_events."},
            "calendar_id": {"type": "string", "description": "Calendar ID (default 'primary')."},
            "summary": {"type": "string"}, "start": {"type": "string"},
            "end": {"type": "string"}, "description": {"type": "string"},
        }, "required": ["event_id"]},
    }},
    {"type": "function", "function": {
        "name": "delete_calendar_event",
        "description": "Delete a Google Calendar event. You must call get_calendar_events first to obtain the real event_id — never guess or invent one.",
        "parameters": {"type": "object", "properties": {
            "event_id": {"type": "string", "description": "Event ID from get_calendar_events."},
            "calendar_id": {"type": "string", "description": "Calendar ID (default 'primary')."},
        }, "required": ["event_id"]},
    }},
    # --- Google Tasks ---
    {"type": "function", "function": {
        "name": "list_task_lists",
        "description": "List all Google Task lists. When searching for a specific task by name, always call this first and then call get_tasks on every list — tasks may be in any list, not just the default.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    }},
    {"type": "function", "function": {
        "name": "get_tasks",
        "description": "Get tasks from a Google Tasks list. There is no server-side search — to find a task by name, fetch all lists via list_task_lists and call get_tasks on each one, then match by substring.",
        "parameters": {"type": "object", "properties": {
            "task_list_id": {"type": "string", "description": "Task list ID (default '@default' = My Tasks)."},
            "show_completed": {"type": "boolean", "description": "Include completed tasks (default false)."},
        }, "required": []},
    }},
    {"type": "function", "function": {
        "name": "create_task",
        "description": "Create a new task in a Google Tasks list.",
        "parameters": {"type": "object", "properties": {
            "title": {"type": "string", "description": "Task title."},
            "task_list_id": {"type": "string", "description": "Task list ID (default '@default')."},
            "notes": {"type": "string", "description": "Task notes (optional)."},
            "due": {"type": "string", "description": "Due date in RFC 3339 format (optional)."},
        }, "required": ["title"]},
    }},
    {"type": "function", "function": {
        "name": "complete_task",
        "description": "Mark a Google Task as completed. You must call get_tasks first to obtain the real task_id — never guess or invent one.",
        "parameters": {"type": "object", "properties": {
            "task_id": {"type": "string", "description": "Task ID from get_tasks."},
            "task_list_id": {"type": "string", "description": "Task list ID (default '@default')."},
        }, "required": ["task_id"]},
    }},
    {"type": "function", "function": {
        "name": "update_task",
        "description": "Update the title, notes, or due date of a Google Task. You must call get_tasks first to obtain the real task_id — never guess or invent one.",
        "parameters": {"type": "object", "properties": {
            "task_id": {"type": "string", "description": "Task ID from get_tasks."},
            "task_list_id": {"type": "string", "description": "Task list ID (default '@default')."},
            "title": {"type": "string"}, "notes": {"type": "string"}, "due": {"type": "string"},
        }, "required": ["task_id"]},
    }},
    {"type": "function", "function": {
        "name": "delete_task",
        "description": "Delete a task from a Google Tasks list. You must call get_tasks first to obtain the real task_id — never guess or invent one.",
        "parameters": {"type": "object", "properties": {
            "task_id": {"type": "string", "description": "Task ID from get_tasks."},
            "task_list_id": {"type": "string", "description": "Task list ID (default '@default')."},
        }, "required": ["task_id"]},
    }},
    # --- Google Drive (read-only) ---
    {"type": "function", "function": {
        "name": "search_drive",
        "description": "Full-text search across Google Drive. Returns file IDs, names, types, and links.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "Search query."},
            "max_results": {"type": "integer", "description": "Max results (default 10)."},
        }, "required": ["query"]},
    }},
    {"type": "function", "function": {
        "name": "get_drive_file",
        "description": "Get metadata and a plain-text preview (up to 2000 chars) of a Google Drive file.",
        "parameters": {"type": "object", "properties": {
            "file_id": {"type": "string", "description": "File ID from search_drive."},
        }, "required": ["file_id"]},
    }},
]

# Synthetic tool definition for get_recent_reactions — injected server-side before every
# probe, not offered to the model as a callable tool.
_GET_REACTIONS_TOOL_DEF = {
    "type": "function",
    "function": {"name": "get_recent_reactions", "description": "Returns recent messages with their IDs and any emoji reactions. Use the message IDs with react_to_message.", "parameters": {"type": "object", "properties": {}, "required": []}},
}


def _build_reactions_injection(conv_id: str, window: int) -> list[dict] | None:
    """
    Inject context about recent messages and their reactions.
    Returns [assistant tool_call msg, tool result msg], or None if there are no messages.
    Includes all messages in the window with their IDs so Mara can call react_to_message.
    """
    import json as _json
    # Fetch recent messages to give Mara valid IDs
    recent_msgs = conn().execute(
        "SELECT id, role, content FROM messages WHERE conversation_id = ? ORDER BY rowid DESC LIMIT ?",
        (conv_id, window),
    ).fetchall()
    if not recent_msgs:
        return None
    recent_msgs = list(reversed(recent_msgs))  # chronological order

    # Fetch reactions for those messages
    reaction_rows = db.get_reactions_for_conversation(conn(), conv_id, limit=window)
    reactions_by_msg: dict = {}
    for r in reaction_rows:
        reactions_by_msg.setdefault(r["message_id"], []).append(
            {"author": r["author"], "emoji": r["emoji"]}
        )

    payload = {
        "recent_messages": [
            {
                "id": m["id"],
                "role": m["role"],
                "preview": (m["content"] or "")[:80],
                "reactions": reactions_by_msg.get(m["id"], []),
            }
            for m in recent_msgs
        ]
    }
    tool_call_id = "rxn000001"
    return [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "id": tool_call_id,
                "type": "function",
                "function": {"name": "get_recent_reactions", "arguments": "{}"},
            }],
        },
        {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": _json.dumps(payload),
        },
    ]


async def execute_tool(name: str, arguments: dict) -> str:
    """Execute a tool by name and return the result as a JSON string."""
    import json
    if name == "get_datetime":
        return json.dumps(tool_get_datetime(arguments.get("timezone")))
    if name == "get_system_info":
        return json.dumps(tool_get_system_info())
    if name == "get_location":
        return json.dumps(await tool_get_location(conn()))
    if name == "get_weather":
        return json.dumps(await tool_get_weather(
            lat=arguments.get("lat"),
            lon=arguments.get("lon"),
            conn=conn(),
        ))
    if name == "store_memory":
        result = _store_memory(
            conn(),
            subject=arguments.get("subject", ""),
            predicate=arguments.get("predicate", ""),
            object_=arguments.get("object", ""),
            source_conv_id=arguments.get("source_conv_id"),
            ttl_hours=arguments.get("ttl_hours", 24.0),
            pinned=bool(arguments.get("pinned", False)),
        )
        await _embed_memory(conn(), result["id"], result["subject"], result["predicate"], result["object"])
        return json.dumps(result)
    if name == "search_memories":
        return json.dumps(await _search_memories(conn(), arguments.get("query", "")))
    if name == "list_memories":
        return json.dumps(_list_memories(conn()))
    if name == "delete_memory":
        deleted = _delete_memory(conn(), arguments.get("memory_id", ""))
        return json.dumps({"deleted": deleted})
    if name == "pin_memory":
        result = _set_pinned(conn(), arguments.get("memory_id", ""), bool(arguments.get("pinned", True)))
        if result is None:
            return json.dumps({"error": "Memory not found"})
        return json.dumps(result)
    if name == "web_search":
        return json.dumps(await _web_search(
            conn(),
            query=arguments.get("query", ""),
            max_results=arguments.get("max_results", 5),
        ))
    if name == "react_to_message":
        message_id = arguments.get("message_id", "")
        emoji = arguments.get("emoji", "")
        msg_row = conn().execute("SELECT id FROM messages WHERE id = ?", (message_id,)).fetchone()
        if not msg_row:
            return json.dumps({"error": f"Message {message_id} not found"})
        import uuid as _uuid
        with db.transaction(conn()):
            row = db.add_reaction(conn(), str(_uuid.uuid4()), message_id, "assistant", emoji)
        return json.dumps({"reaction": dict(row)})
    # --- Reminders ---
    if name == "set_reminder":
        message = arguments.get("message", "")
        fire_at = arguments.get("fire_at", "")
        log.info("set_reminder called: message=%r fire_at=%r", message, fire_at)
        if not message or not fire_at:
            return json.dumps({"error": "message and fire_at are required"})
        try:
            from .events.watcher import get_registry
            from datetime import datetime as _dt, timezone as _tz
            # Validate fire_at is in the future — reject stale dates outright
            _fire_dt = _dt.fromisoformat(fire_at)
            if _fire_dt.tzinfo is None:
                _fire_dt = _fire_dt.astimezone()
            _delay = (_fire_dt - _dt.now(_tz.utc)).total_seconds()
            if _delay < 0:
                return json.dumps({"error": f"fire_at '{fire_at}' is in the past. Call get_datetime first to get the current time, then construct a future fire_at."})
            watcher = make_alarm_watcher(message, fire_at)
            log.info("set_reminder: created watcher id=%s fire_at=%s poll_fn=%s", watcher.id, watcher.fire_at, watcher._poll_fn)
            registry = get_registry()
            registry.register(watcher)
            log.info("set_reminder: registered. registry now has %d watchers", len(registry.all()))
            registry._start_watcher(watcher)
            log.info("set_reminder: task started: task=%s", watcher._task)
            with db.transaction(conn()):
                _db_save_watcher(conn(), watcher.id, watcher.source_type, watcher.name, watcher.description, watcher.fire_at)
            log.info("set_reminder: persisted to DB")
            return json.dumps({
                "ok": True,
                "watcher_id": watcher.id,
                "message": message,
                "fire_at": watcher.fire_at,
            })
        except Exception as exc:
            log.error("set_reminder: exception: %s", exc, exc_info=True)
            return json.dumps({"error": str(exc)})
    # --- Google tools ---
    if name == "list_calendars":
        return json.dumps(_list_calendars(conn()))
    if name == "get_calendar_events":
        return json.dumps(_get_calendar_events(
            conn(),
            calendar_id=arguments.get("calendar_id", "primary"),
            time_min=arguments.get("time_min"),
            time_max=arguments.get("time_max"),
            max_results=arguments.get("max_results", 10),
        ))
    if name == "create_calendar_event":
        return json.dumps(_create_calendar_event(
            conn(),
            summary=arguments.get("summary", ""),
            start=arguments.get("start", ""),
            end=arguments.get("end", ""),
            calendar_id=arguments.get("calendar_id", "primary"),
            description=arguments.get("description", ""),
            attendees=arguments.get("attendees"),
        ))
    if name == "update_calendar_event":
        return json.dumps(_update_calendar_event(
            conn(),
            event_id=arguments.get("event_id", ""),
            calendar_id=arguments.get("calendar_id", "primary"),
            summary=arguments.get("summary"),
            start=arguments.get("start"),
            end=arguments.get("end"),
            description=arguments.get("description"),
        ))
    if name == "delete_calendar_event":
        return json.dumps(_delete_calendar_event(
            conn(),
            event_id=arguments.get("event_id", ""),
            calendar_id=arguments.get("calendar_id", "primary"),
        ))
    if name == "list_task_lists":
        return json.dumps(_list_task_lists(conn()))
    if name == "get_tasks":
        return json.dumps(_get_tasks(
            conn(),
            task_list_id=arguments.get("task_list_id", "@default"),
            show_completed=bool(arguments.get("show_completed", False)),
        ))
    if name == "create_task":
        return json.dumps(_create_task(
            conn(),
            title=arguments.get("title", ""),
            task_list_id=arguments.get("task_list_id", "@default"),
            notes=arguments.get("notes", ""),
            due=arguments.get("due"),
        ))
    if name == "complete_task":
        return json.dumps(_complete_task(
            conn(),
            task_id=arguments.get("task_id", ""),
            task_list_id=arguments.get("task_list_id", "@default"),
        ))
    if name == "update_task":
        return json.dumps(_update_task(
            conn(),
            task_id=arguments.get("task_id", ""),
            task_list_id=arguments.get("task_list_id", "@default"),
            title=arguments.get("title"),
            notes=arguments.get("notes"),
            due=arguments.get("due"),
        ))
    if name == "delete_task":
        return json.dumps(_delete_task(
            conn(),
            task_id=arguments.get("task_id", ""),
            task_list_id=arguments.get("task_list_id", "@default"),
        ))
    if name == "search_drive":
        return json.dumps(_search_drive(
            conn(),
            query=arguments.get("query", ""),
            max_results=arguments.get("max_results", 10),
        ))
    if name == "get_drive_file":
        return json.dumps(_get_drive_file(conn(), file_id=arguments.get("file_id", "")))
    return json.dumps({"error": f"Unknown tool: {name}"})


def conn():
    return _conn


class _LockedConn:
    """Thin proxy that serializes all sqlite3 calls through a shared lock."""

    def __init__(self, connection: sqlite3.Connection, lock: threading.Lock):
        self._conn = connection
        self._lock = lock

    def execute(self, sql, parameters=()):
        with self._lock:
            return self._conn.execute(sql, parameters)

    def executemany(self, sql, seq):
        with self._lock:
            return self._conn.executemany(sql, seq)

    def commit(self):
        with self._lock:
            self._conn.commit()

    def rollback(self):
        with self._lock:
            self._conn.rollback()

    def close(self):
        self._conn.close()

    def __getattr__(self, name):
        return getattr(self._conn, name)


# --- Pydantic models ---

class Message(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str


class ChatRequest(BaseModel):
    conversation_id: str | None = None
    model: str = "Mistral-Large-3"
    messages: list[Message]
    max_tokens: int = Field(default=2048, ge=1, le=16384)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    stream: bool = True
    context_window: int | None = Field(default=None, ge=1, le=200)
    is_retry: bool = False


class ConversationCreate(BaseModel):
    title: str = "New conversation"
    model: str = "Mistral-Large-3"


class ConversationUpdate(BaseModel):
    title: str | None = None
    model: str | None = None


# --- Health ---

@app.get("/v1/health")
async def health():
    return await provider_router.get_health()


# --- Conversations ---

@app.get("/v1/conversations")
def list_convs():
    rows = db.list_conversations(conn())
    return [dict(r) for r in rows]


@app.post("/v1/conversations", status_code=201)
def create_conv(body: ConversationCreate):
    conv_id = str(uuid.uuid4())
    provider = "azure"
    with db.transaction(conn()):
        row = db.create_conversation(conn(), conv_id, body.title, body.model, provider)
    return dict(row)


@app.get("/v1/conversations/{conv_id}")
def get_conv(conv_id: str):
    row = db.get_conversation(conn(), conv_id)
    if not row:
        raise HTTPException(404, "Conversation not found")
    messages = db.get_messages(conn(), conv_id)
    return {**dict(row), "messages": [dict(m) for m in messages]}


@app.patch("/v1/conversations/{conv_id}")
def patch_conv(conv_id: str, body: ConversationUpdate):
    row = db.get_conversation(conn(), conv_id)
    if not row:
        raise HTTPException(404, "Conversation not found")
    if body.title is None and body.model is None:
        return dict(row)
    with db.transaction(conn()):
        row = db.update_conversation(conn(), conv_id, body.title, body.model)
    return dict(row)


@app.delete("/v1/conversations/{conv_id}", status_code=204)
def delete_conv(conv_id: str):
    db.delete_conversation(conn(), conv_id)
    conn().commit()


@app.delete("/v1/conversations/{conv_id}/messages/{msg_id}", status_code=204)
def delete_message(conv_id: str, msg_id: str):
    found = db.delete_message(conn(), msg_id)
    if not found:
        raise HTTPException(404, "Message not found")
    conn().commit()


@app.post("/v1/conversations/{conv_id}/embed")
async def embed_conv(conv_id: str):
    """Embed a conversation's assistant turns into the RAG store."""
    row = db.get_conversation(conn(), conv_id)
    if not row:
        raise HTTPException(404, "Conversation not found")
    await embed_conversation(conn(), conv_id)
    return {"status": "ok"}


# --- Chat completions (streaming) ---

@app.post("/v1/chat/completions")
async def chat_completions(body: ChatRequest):
    # Ensure conversation exists
    conv_id = body.conversation_id or str(uuid.uuid4())
    if not db.get_conversation(conn(), conv_id):
        with db.transaction(conn()):
            db.create_conversation(conn(), conv_id, "New conversation", body.model, "azure")

    # Persist user message (skip on retry — already in the database)
    last_user = next((m for m in reversed(body.messages) if m.role == "user"), None)
    user_msg_id = str(uuid.uuid4())
    if last_user and not body.is_retry:
        with db.transaction(conn()):
            db.insert_message(conn(), user_msg_id, conv_id, "user", last_user.content, model=None)

    # Apply rolling context window.
    # Strip empty-content assistant messages with no tool_calls — these can appear
    # in history when Mara reacted-only and the DB row was persisted before the fix.
    # Mistral rejects such messages with "must have either content or tool_calls".
    messages_for_model = [
        m.model_dump() for m in body.messages
        if not (m.role == "assistant" and not (m.content or "").strip() and not getattr(m, "tool_calls", None))
    ]
    window = body.context_window or CONTEXT_WINDOW
    if len(messages_for_model) > window:
        # Always preserve a leading system message if present
        if messages_for_model[0]["role"] == "system":
            messages_for_model = [messages_for_model[0]] + messages_for_model[-(window - 1):]
        else:
            messages_for_model = messages_for_model[-window:]

    # Collect message IDs currently in the window so RAG skips what's already present.
    # The frontend sends full content but not IDs, so we match by content against DB rows.
    windowed_content = {m["content"] for m in messages_for_model if m.get("role") == "assistant"}
    in_window_msg_ids: set[str] = set()
    if windowed_content:
        db_rows = conn().execute(
            "SELECT id, content FROM messages WHERE conversation_id = ? AND role = 'assistant'",
            (conv_id,),
        ).fetchall()
        for row in db_rows:
            if row["content"] in windowed_content:
                in_window_msg_ids.add(row["id"])

    # Inject structured memories as a system message immediately after the persona prompt
    memory_text = _memories_as_text(conn())
    if memory_text:
        mem_msg = {"role": "system", "content": memory_text}
        if messages_for_model and messages_for_model[0]["role"] == "system":
            messages_for_model.insert(1, mem_msg)
        else:
            messages_for_model.insert(0, mem_msg)

    # Inject RAG context — searches all conversations, skips messages already in the window
    if last_user:
        rag_chunks = await retrieve_context(conn(), last_user.content, exclude_message_ids=in_window_msg_ids)
        if rag_chunks:
            rag_text = "\n\n".join(c["chunk_text"] for c in rag_chunks)
            rag_msg = {"role": "system", "content": f"Relevant context from memory:\n{rag_text}"}
            if messages_for_model and messages_for_model[0]["role"] == "system":
                messages_for_model.insert(1, rag_msg)
            else:
                messages_for_model.insert(0, rag_msg)

    # Inject recent reactions as a synthetic tool call so Mara sees them in context.
    # Appended at the end so the sequence is: …user → assistant(tool_call) → tool result
    # which is the valid order Mistral requires before a model turn.
    if conv_id:
        reactions_injection = _build_reactions_injection(conv_id, window)
        if reactions_injection:
            messages_for_model.extend(reactions_injection)

    # --- Tool-use loop ---
    # Allows up to MAX_TOOL_ROUNDS sequential rounds of tool calls before
    # streaming the final answer. This lets Mara fetch data in one round and
    # act on it (e.g. update/delete) in the next.
    import json as _json

    MAX_TOOL_ROUNDS = 5
    tools_used: list[dict] = []  # [{name, ...}] — forwarded to frontend in done event
    provider = resolved_model = None

    for _round in range(MAX_TOOL_ROUNDS):
        try:
            provider, resolved_model, tool_msg = await provider_router.call_with_tools(
                body.model,
                messages_for_model,
                TOOLS,
                body.max_tokens,
            )
        except RuntimeError as exc:
            error_msg = str(exc)
            async def error_stream():
                yield f"data: {_json.dumps({'type': 'error', 'message': error_msg})}\n\n"
            return StreamingResponse(error_stream(), media_type="text/event-stream")

        tool_calls = tool_msg.get("tool_calls") or []
        if not tool_calls:
            break  # No more tool calls — proceed to streaming the final answer

        # Append the assistant's tool-call message to the conversation
        messages_for_model.append(tool_msg)
        # Execute each tool and append results
        for tc in tool_calls:
            fn = tc["function"]
            try:
                args = _json.loads(fn.get("arguments") or "{}")
            except _json.JSONDecodeError:
                args = {}
            result = await execute_tool(fn["name"], args)
            tool_entry: dict = {"name": fn["name"]}
            if fn["name"] == "web_search":
                tool_entry["query"] = args.get("query", "")
                try:
                    parsed = _json.loads(result)
                    tool_entry["results"] = parsed.get("results", [])
                except Exception:
                    tool_entry["results"] = []
            elif fn["name"] == "get_weather":
                try:
                    parsed = _json.loads(result)
                    if "current" in parsed:
                        tool_entry["weather"] = parsed
                except Exception:
                    pass
            elif fn["name"] == "react_to_message":
                try:
                    parsed = _json.loads(result)
                    tool_entry["reaction"] = parsed.get("reaction")
                except Exception:
                    pass
            tools_used.append(tool_entry)
            messages_for_model.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": result,
            })

    # Stream the final response (with tool results in context if any were called)
    provider, resolved_model, stream_iter = await provider_router.stream_chat(
        body.model,
        messages_for_model,
        body.max_tokens,
        body.temperature,
    )

    if not body.stream:
        # Collect full response
        full_text = ""
        prompt_tokens = 0
        completion_tokens = 0
        async for chunk in stream_iter:
            if chunk["type"] == "delta":
                full_text += chunk["content"]
            elif chunk["type"] == "usage":
                prompt_tokens = chunk["prompt_tokens"]
                completion_tokens = chunk["completion_tokens"]
            elif chunk["type"] == "error":
                raise HTTPException(502, chunk["message"])

        msg_id = str(uuid.uuid4())
        with db.transaction(conn()):
            db.insert_message(conn(), msg_id, conv_id, "assistant", full_text, model=resolved_model, tools_used=tools_used or None)
        cost = record_usage(conn(), str(uuid.uuid4()), conv_id, msg_id, provider, resolved_model,
                            prompt_tokens, completion_tokens)
        try:
            await embed_message(conn(), conv_id, msg_id, full_text)
        except Exception:
            pass
        return {
            "conversation_id": conv_id,
            "model": resolved_model,
            "provider": provider,
            "message": {"role": "assistant", "content": full_text},
            "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens, "cost_usd": cost},
            "tools_used": tools_used,
        }

    # Streaming response — SSE
    async def event_stream():
        full_text = ""
        prompt_tokens = 0
        completion_tokens = 0
        import json

        async for chunk in stream_iter:
            if chunk["type"] == "delta":
                full_text += chunk["content"]
                yield f"data: {json.dumps({'type': 'delta', 'content': chunk['content'], 'conversation_id': conv_id})}\n\n"
            elif chunk["type"] == "usage":
                prompt_tokens = chunk["prompt_tokens"]
                completion_tokens = chunk["completion_tokens"]
            elif chunk["type"] == "error":
                yield f"data: {json.dumps({'type': 'error', 'message': chunk['message']})}\n\n"
                return

        # Persist assistant reply + usage after stream ends.
        # If the model produced no text (e.g. only called tools like react_to_message),
        # skip persisting an empty message and signal the frontend to drop the placeholder.
        if not full_text.strip():
            yield f"data: {json.dumps({'type': 'done', 'conversation_id': conv_id, 'model': resolved_model, 'provider': provider, 'user_msg_id': user_msg_id, 'assistant_msg_id': None, 'empty': True, 'usage': {'prompt_tokens': prompt_tokens, 'completion_tokens': completion_tokens, 'cost_usd': 0.0}, 'tools_used': tools_used})}\n\n"
            return

        msg_id = str(uuid.uuid4())
        with db.transaction(conn()):
            db.insert_message(conn(), msg_id, conv_id, "assistant", full_text, model=resolved_model, tools_used=tools_used or None)
        cost = record_usage(conn(), str(uuid.uuid4()), conv_id, msg_id, provider, resolved_model,
                            prompt_tokens, completion_tokens)
        # Send done before embedding — embedding calls Azure and must not block or error the response
        yield f"data: {json.dumps({'type': 'done', 'conversation_id': conv_id, 'model': resolved_model, 'provider': provider, 'user_msg_id': user_msg_id, 'assistant_msg_id': msg_id, 'usage': {'prompt_tokens': prompt_tokens, 'completion_tokens': completion_tokens, 'cost_usd': cost}, 'tools_used': tools_used})}\n\n"
        try:
            await embed_message(conn(), conv_id, msg_id, full_text)
        except Exception:
            pass  # embedding failure is non-fatal; RAG will just miss this message

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# --- Memory CRUD ---

class MemoryCreate(BaseModel):
    subject: str
    predicate: str
    object: str
    ttl_hours: float | None = 24.0
    pinned: bool = False

class MemoryUpdate(BaseModel):
    subject: str | None = None
    predicate: str | None = None
    object: str | None = None
    ttl_hours: float | None = None
    pinned: bool | None = None


@app.get("/v1/memories")
async def list_memories_endpoint(q: str | None = None):
    if q:
        return await _search_memories(conn(), q)
    return _list_memories(conn())


@app.post("/v1/memories", status_code=201)
async def create_memory(body: MemoryCreate):
    result = _store_memory(conn(), body.subject, body.predicate, body.object,
                           ttl_hours=body.ttl_hours, pinned=body.pinned)
    await _embed_memory(conn(), result["id"], result["subject"], result["predicate"], result["object"])
    return result


@app.patch("/v1/memories/{memory_id}")
async def update_memory(memory_id: str, body: MemoryUpdate):
    row = conn().execute("SELECT * FROM memories WHERE id = ?", (memory_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Memory not found")
    # Special case: only toggling pin
    if body.subject is None and body.predicate is None and body.object is None and body.pinned is not None:
        result = _set_pinned(conn(), memory_id, body.pinned)
        return result
    new_subject   = body.subject   if body.subject   is not None else row["subject"]
    new_predicate = body.predicate if body.predicate is not None else row["predicate"]
    new_object    = body.object    if body.object    is not None else row["object"]
    new_ttl       = body.ttl_hours if body.ttl_hours is not None else None
    new_pinned    = body.pinned    if body.pinned    is not None else bool(row["pinned"])
    result = _store_memory(conn(), new_subject, new_predicate, new_object,
                           ttl_hours=new_ttl, pinned=new_pinned)
    await _embed_memory(conn(), result["id"], result["subject"], result["predicate"], result["object"])
    return result


@app.delete("/v1/memories/{memory_id}", status_code=204)
def delete_memory_endpoint(memory_id: str):
    if not _delete_memory(conn(), memory_id):
        raise HTTPException(404, "Memory not found")


# --- Usage / cost ---

@app.get("/v1/usage")
def usage_summary(days: int = 30):
    return {
        "daily": get_daily_costs(conn(), days),
        "by_model": get_model_comparison(conn()),
    }


@app.get("/v1/usage/{conv_id}")
def conversation_usage(conv_id: str):
    return get_conversation_cost(conn(), conv_id)


# --- Pricing ---

class PricingUpdate(BaseModel):
    input_cost_per_1k: float = Field(ge=0.0)
    output_cost_per_1k: float = Field(ge=0.0)


@app.get("/v1/pricing")
def list_pricing_endpoint():
    return list_pricing(conn())


@app.get("/v1/pricing/{provider}/{model:path}")
def get_pricing_endpoint(provider: str, model: str):
    row = get_pricing(conn(), provider, model)
    if not row:
        raise HTTPException(404, "Pricing not found")
    return row


@app.post("/v1/pricing/{provider}/{model:path}", status_code=200)
def upsert_pricing_endpoint(provider: str, model: str, body: PricingUpdate):
    return upsert_pricing(conn(), provider, model, body.input_cost_per_1k, body.output_cost_per_1k)


# --- RAG context retrieval ---

@app.get("/v1/context")
async def get_context(query: str, exclude_conv_id: str | None = None):
    chunks = await retrieve_context(conn(), query, exclude_conv_id)
    return {"chunks": chunks}


# --- Tools manifest ---

@app.get("/v1/tools")
def list_tools():
    return [
        {
            "name": t["function"]["name"],
            "description": t["function"]["description"],
            "parameters": list(t["function"]["parameters"].get("properties", {}).keys()),
            "required": t["function"]["parameters"].get("required", []),
        }
        for t in TOOLS
    ]


# --- Search usage ---

@app.get("/v1/search/usage")
def search_usage():
    return _search_get_usage(conn())


# --- Tokenizer ---

class TokenizeRequest(BaseModel):
    text: str


@app.get("/v1/tokenizer/info")
def tokenizer_info_endpoint():
    from .tools.tokenizer_tool import tokenizer_info
    return tokenizer_info()


@app.post("/v1/tokenizer/tokenize")
def tokenize_endpoint(body: TokenizeRequest):
    from .tools.tokenizer_tool import tokenize
    return tokenize(body.text)


# --- Reactions ---

class ReactionCreate(BaseModel):
    author: Literal["user", "assistant"]
    emoji: str


@app.get("/v1/reactions/{message_id}")
def get_reactions_endpoint(message_id: str):
    rows = db.get_reactions(conn(), message_id)
    return [dict(r) for r in rows]


@app.post("/v1/reactions/{message_id}", status_code=201)
def add_reaction_endpoint(message_id: str, body: ReactionCreate):
    msg_row = conn().execute("SELECT id FROM messages WHERE id = ?", (message_id,)).fetchone()
    if not msg_row:
        raise HTTPException(404, "Message not found")
    with db.transaction(conn()):
        row = db.add_reaction(conn(), str(uuid.uuid4()), message_id, body.author, body.emoji)
    return dict(row)


@app.delete("/v1/reactions/{reaction_id}", status_code=204)
def delete_reaction_endpoint(reaction_id: str):
    found = db.delete_reaction(conn(), reaction_id)
    if not found:
        raise HTTPException(404, "Reaction not found")
    conn().commit()


# --- Google OAuth ---

@app.get("/v1/google/auth-status")
def google_auth_status():
    return _google_auth_status(conn())


@app.post("/v1/google/auth-start")
async def google_auth_start():
    if not os.getenv("GOOGLE_CLIENT_ID") or not os.getenv("GOOGLE_CLIENT_SECRET"):
        raise HTTPException(400, "GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be set in .env")
    return await _google_start_oauth(conn())


@app.post("/v1/google/revoke", status_code=200)
def google_revoke():
    return _google_revoke(conn())


# --- Watchers ---

class WatcherPatch(BaseModel):
    enabled: bool | None = None
    interval_seconds: int | None = None


@app.get("/v1/watchers")
def list_watchers():
    from .events.watcher import get_registry
    return [w.to_dict() for w in get_registry().all()]


@app.patch("/v1/watchers/{watcher_id}")
def patch_watcher(watcher_id: str, body: WatcherPatch):
    from .events.watcher import get_registry
    w = get_registry().patch(watcher_id, enabled=body.enabled, interval_seconds=body.interval_seconds)
    if not w:
        raise HTTPException(404, "Watcher not found")
    with db.transaction(conn()):
        if w.source_type == "alarm" and w.fire_at:
            # Persist enabled state for alarm watchers
            _db_save_watcher(conn(), w.id, w.source_type, w.name, w.description, w.fire_at, w.enabled)
        elif w.source_type in ("calendar", "system", "schedule", "cost"):
            # Persist interval for built-in watchers so it survives restarts
            if body.interval_seconds is not None:
                _db_set_setting(conn(), f"watcher_interval.{w.source_type}", str(w.interval_seconds))
    return w.to_dict()


@app.delete("/v1/watchers/{watcher_id}", status_code=204)
def delete_watcher(watcher_id: str):
    from .events.watcher import get_registry
    if not get_registry().delete(watcher_id):
        raise HTTPException(404, "Watcher not found")


# --- Quiet hours ---

class QuietHoursBody(BaseModel):
    enabled: bool
    start: str  # "HH:MM"
    end: str    # "HH:MM"


@app.get("/v1/quiet-hours")
def get_quiet_hours():
    enabled = _db_get_setting(conn(), "quiet_hours_enabled") or "1"
    start   = _db_get_setting(conn(), "quiet_hours_start")   or "21:00"
    end     = _db_get_setting(conn(), "quiet_hours_end")     or "07:00"
    return {"enabled": enabled != "0", "start": start, "end": end}


@app.put("/v1/quiet-hours")
def put_quiet_hours(body: QuietHoursBody):
    with db.transaction(conn()):
        _db_set_setting(conn(), "quiet_hours_enabled", "1" if body.enabled else "0")
        _db_set_setting(conn(), "quiet_hours_start", body.start)
        _db_set_setting(conn(), "quiet_hours_end", body.end)
    return {"enabled": body.enabled, "start": body.start, "end": body.end}


# --- Cost alert threshold sync ---

class CostAlertBody(BaseModel):
    threshold: float | None  # None = disabled


@app.put("/v1/settings/cost-alert")
def put_cost_alert(body: CostAlertBody):
    with db.transaction(conn()):
        if body.threshold is None or body.threshold <= 0:
            _db_set_setting(conn(), "cost_alert_threshold", "")
        else:
            _db_set_setting(conn(), "cost_alert_threshold", str(body.threshold))
    return {"threshold": body.threshold}


# --- Event handling: generate Mara reply in the context of a conversation ---

class EventHandleRequest(BaseModel):
    conversation_id: str
    watcher_name: str
    title: str
    body: str


@app.post("/v1/events/handle")
async def handle_event(body: EventHandleRequest):
    """
    Called by the frontend when a watcher event fires.
    Injects the event as a synthetic tool-call/result pair (not a visible user message)
    so Mara sees the trigger in context without it appearing in the conversation thread.
    Only the assistant reply is persisted and returned.
    """
    import json as _json

    conv_id = body.conversation_id
    if not db.get_conversation(conn(), conv_id):
        raise HTTPException(404, "Conversation not found")

    # Load existing messages to provide context
    existing = db.get_messages(conn(), conv_id)

    # Build messages for the model
    messages_for_model: list[dict] = []

    # Leading system message from conversation if any
    sys_rows = [m for m in existing if m["role"] == "system"]
    if sys_rows:
        messages_for_model.append({"role": "system", "content": sys_rows[-1]["content"]})

    # Inject memories right after system prompt
    memory_text = _memories_as_text(conn())
    if memory_text:
        insert_at = 1 if messages_for_model and messages_for_model[0]["role"] == "system" else 0
        messages_for_model.insert(insert_at, {"role": "system", "content": memory_text})

    # Recent conversation history — skip tool-role messages (no tools declared here)
    non_sys = [m for m in existing if m["role"] not in ("system", "tool")]
    for m in non_sys[-CONTEXT_WINDOW:]:
        messages_for_model.append({"role": m["role"], "content": m["content"]})

    # Inject as a user turn — Mistral requires last role to be user/tool before generating.
    # This message is never shown to the user; only the assistant reply is persisted.
    messages_for_model.append({
        "role": "user",
        "content": (
            f"[Automated reminder] {body.watcher_name}: {body.title} — {body.body}\n"
            "(This is an automated event, not a message I typed. Respond naturally in the "
            "context of our conversation. Be concise and direct.)"
        ),
    })

    log.info("handle_event: sending %d messages to model", len(messages_for_model))
    for i, m in enumerate(messages_for_model):
        log.info("  [%d] role=%s content=%.120s", i, m.get("role"), str(m.get("content", ""))[:120])

    try:
        _, resolved_model, stream_iter = await provider_router.stream_chat(
            "Mistral-Large-3",
            messages_for_model,
            max_tokens=512,
            temperature=0.4,
        )
    except Exception as exc:
        log.error("handle_event: stream_chat raised: %s", exc)
        raise HTTPException(502, str(exc))

    full_text = ""
    async for chunk in stream_iter:
        if chunk["type"] == "delta":
            full_text += chunk["content"]
        elif chunk["type"] == "error":
            err_msg = chunk.get("message", "model error")
            log.error("handle_event: model error: %s", err_msg[:300])
            raise HTTPException(502, err_msg)

    if not full_text.strip():
        raise HTTPException(502, "Model returned empty response")

    # Persist only the assistant reply — no visible user message
    reply_msg_id = str(uuid.uuid4())
    with db.transaction(conn()):
        db.insert_message(conn(), reply_msg_id, conv_id, "assistant", full_text, model=resolved_model)

    try:
        await embed_message(conn(), conv_id, reply_msg_id, full_text)
    except Exception:
        pass

    return {
        "assistant_message": {
            "id": reply_msg_id,
            "role": "assistant",
            "content": full_text,
            "conversation_id": conv_id,
            "model": resolved_model,
        },
    }


# --- Notifications SSE stream ---

@app.get("/v1/notifications")
async def notifications_stream():
    """SSE stream — pushes notification payloads as they fire."""
    import json as _json

    q: asyncio.Queue = asyncio.Queue(maxsize=50)
    add_sse_client(q)

    async def event_gen():
        try:
            yield "data: {\"type\": \"connected\"}\n\n"
            while True:
                payload = await q.get()
                yield f"data: {_json.dumps(payload)}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            remove_sse_client(q)

    return StreamingResponse(event_gen(), media_type="text/event-stream")
