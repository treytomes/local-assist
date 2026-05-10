"""
MCP server mounted onto the existing FastAPI app.
Exposes tools that the chat endpoint can call on behalf of the model.
"""
from mcp.server.fastmcp import FastMCP
from .tools.datetime_tool import get_datetime as _get_datetime
from .tools.system_info_tool import get_system_info as _get_system_info
from .tools.location_tool import get_location as _get_location
from .tools.weather_tool import get_weather as _get_weather
from .tools.memory_tool import (
    store_memory as _store_memory,
    embed_memory as _embed_memory,
    search_memories as _search_memories,
    list_memories as _list_memories,
    set_pinned as _set_pinned,
    delete_memory as _delete_memory,
)
from .tools.search import web_search as _web_search
from .tools.google import (
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
from .database import shared_connection

mcp = FastMCP(
    name="local-assist",
    instructions="Tools available to Mara, the local AI assistant.",
)


@mcp.tool()
def get_datetime(timezone: str | None = None) -> dict:
    """
    Returns the current date, time, and timezone.

    Args:
        timezone: Optional IANA timezone name (e.g. "America/Chicago", "Europe/London").
                  If omitted, uses the system local timezone.
    """
    return _get_datetime(timezone)


@mcp.tool()
def get_system_info() -> dict:
    """
    Returns a snapshot of the host machine's hardware and OS state, including:
    OS version, CPU model and core count, current CPU usage per core, RAM and swap
    usage, GPU details, and system model name if available.
    Use this when asked about the machine's specs, performance, memory, or hardware.
    """
    return _get_system_info()


@mcp.tool()
async def get_location() -> dict:
    """
    Returns current location (city, region, country, lat/lon, timezone) via IP geolocation.
    Checks memory for a user-configured override first.
    """
    return await _get_location(shared_connection())


@mcp.tool()
async def get_weather(lat: float | None = None, lon: float | None = None) -> dict:
    """
    Returns current weather conditions and a 7-day forecast.
    Resolves location automatically if lat/lon are omitted.
    Temperatures in °F, wind in mph, precipitation in inches.
    """
    return await _get_weather(lat=lat, lon=lon, conn=shared_connection())


@mcp.tool()
async def store_memory(
    subject: str,
    predicate: str,
    object: str,
    ttl_hours: float | None = 24.0,
    pinned: bool = False,
) -> dict:
    """
    Store a fact as a subject/predicate/object triple. Overwrites any existing
    memory with the same subject+predicate pair.

    Args:
        subject:   Entity the fact is about (e.g. "user", "project", "mara").
        predicate: Relationship or property (e.g. "prefers", "is working on").
        object:    Value of the fact. Prefer full sentences when context matters — include
                   the why and the texture, not just the bare fact. "dislikes mornings,
                   finds them disorienting" is more useful than "hates mornings".
        ttl_hours: Hours until this memory expires. Default 24. Ignored when pinned=True.
        pinned:    If True, this memory never expires.
    """
    result = _store_memory(shared_connection(), subject, predicate, object,
                           ttl_hours=ttl_hours, pinned=pinned)
    await _embed_memory(shared_connection(), result["id"], subject, predicate, object)
    return result


@mcp.tool()
async def search_memories(query: str) -> list[dict]:
    """
    Semantic vector search over stored memories (falls back to keyword search).

    Args:
        query: Natural language query — finds semantically related memories.
    """
    return await _search_memories(shared_connection(), query)


@mcp.tool()
def list_memories() -> list[dict]:
    """Return all live (non-expired) memories, pinned first."""
    return _list_memories(shared_connection())


@mcp.tool()
def pin_memory(memory_id: str, pinned: bool = True) -> dict:
    """
    Pin or unpin a memory. Pinned memories never expire.
    Unpinning restores the default 24-hour decay.

    Args:
        memory_id: The ID of the memory to pin/unpin.
        pinned:    True to pin, False to unpin.
    """
    result = _set_pinned(shared_connection(), memory_id, pinned)
    if result is None:
        return {"error": "Memory not found"}
    return result


@mcp.tool()
async def web_search(query: str, max_results: int = 5) -> dict:
    """
    Search the web for current information using Tavily.
    Use this when the user asks about recent events, live data, or anything
    training data may not cover. Returns titles, URLs, and content snippets.

    Args:
        query:       The search query.
        max_results: Number of results to return (1–10, default 5).
    """
    return await _web_search(shared_connection(), query=query, max_results=max_results)


@mcp.tool()
def delete_memory(memory_id: str) -> dict:
    """
    Delete a stored memory by ID.

    Args:
        memory_id: The ID returned when the memory was stored.
    """
    deleted = _delete_memory(shared_connection(), memory_id)
    return {"deleted": deleted}


@mcp.tool()
def list_calendars() -> dict:
    """List all Google Calendars. Call this first to get calendar IDs."""
    return _list_calendars(shared_connection())


@mcp.tool()
def get_calendar_events(
    calendar_id: str = "primary",
    time_min: str | None = None,
    time_max: str | None = None,
    max_results: int = 10,
) -> dict:
    """
    Fetch events from a Google Calendar.

    Args:
        calendar_id: Calendar ID from list_calendars, or 'primary'.
        time_min:    RFC 3339 start datetime (default: now).
        time_max:    RFC 3339 end datetime (optional).
        max_results: Max events to return (default 10).
    """
    return _get_calendar_events(shared_connection(), calendar_id, time_min, time_max, max_results)


@mcp.tool()
def create_calendar_event(
    summary: str,
    start: str,
    end: str,
    calendar_id: str = "primary",
    description: str = "",
    attendees: list[str] | None = None,
) -> dict:
    """
    Create a new Google Calendar event.

    Args:
        summary:     Event title.
        start:       RFC 3339 start datetime.
        end:         RFC 3339 end datetime.
        calendar_id: Calendar ID (default 'primary').
        description: Event description (optional).
        attendees:   List of attendee email addresses (optional).
    """
    return _create_calendar_event(shared_connection(), summary, start, end, calendar_id, description, attendees)


@mcp.tool()
def update_calendar_event(
    event_id: str,
    calendar_id: str = "primary",
    summary: str | None = None,
    start: str | None = None,
    end: str | None = None,
    description: str | None = None,
) -> dict:
    """Update fields on an existing Google Calendar event."""
    return _update_calendar_event(shared_connection(), event_id, calendar_id, summary, start, end, description)


@mcp.tool()
def delete_calendar_event(event_id: str, calendar_id: str = "primary") -> dict:
    """Delete a Google Calendar event."""
    return _delete_calendar_event(shared_connection(), event_id, calendar_id)


@mcp.tool()
def list_task_lists() -> dict:
    """List all Google Task lists."""
    return _list_task_lists(shared_connection())


@mcp.tool()
def get_tasks(task_list_id: str = "@default", show_completed: bool = False) -> dict:
    """
    Get tasks from a Google Tasks list.

    Args:
        task_list_id:   Task list ID (default '@default' = My Tasks).
        show_completed: Include completed tasks (default false).
    """
    return _get_tasks(shared_connection(), task_list_id, show_completed)


@mcp.tool()
def create_task(
    title: str,
    task_list_id: str = "@default",
    notes: str = "",
    due: str | None = None,
) -> dict:
    """
    Create a new Google Task.

    Args:
        title:        Task title.
        task_list_id: Task list ID (default '@default').
        notes:        Task notes (optional).
        due:          Due date in RFC 3339 format (optional).
    """
    return _create_task(shared_connection(), title, task_list_id, notes, due)


@mcp.tool()
def complete_task(task_id: str, task_list_id: str = "@default") -> dict:
    """Mark a Google Task as completed."""
    return _complete_task(shared_connection(), task_id, task_list_id)


@mcp.tool()
def update_task(
    task_id: str,
    task_list_id: str = "@default",
    title: str | None = None,
    notes: str | None = None,
    due: str | None = None,
) -> dict:
    """Update the title, notes, or due date of a Google Task."""
    return _update_task(shared_connection(), task_id, task_list_id, title, notes, due)


@mcp.tool()
def delete_task(task_id: str, task_list_id: str = "@default") -> dict:
    """Delete a task from a Google Tasks list."""
    return _delete_task(shared_connection(), task_id, task_list_id)


@mcp.tool()
def search_drive(query: str, max_results: int = 10) -> dict:
    """
    Full-text search across Google Drive.

    Args:
        query:       Search query.
        max_results: Max results (default 10).
    """
    return _search_drive(shared_connection(), query, max_results)


@mcp.tool()
def get_drive_file(file_id: str) -> dict:
    """
    Get metadata and a plain-text preview (up to 2000 chars) of a Google Drive file.

    Args:
        file_id: File ID from search_drive.
    """
    return _get_drive_file(shared_connection(), file_id)


@mcp.tool()
def set_reminder(message: str, fire_at: str) -> dict:
    """
    Set a one-shot reminder that fires at a specific date and time.
    Mara will proactively surface the message in the active conversation at that time.
    Always call get_datetime first so you know the current time before constructing fire_at.
    Reminders are in-memory only and lost if the app restarts before they fire.

    Args:
        message: The reminder message to surface when the alarm fires.
        fire_at: ISO 8601 datetime when the reminder should fire (e.g. '2026-05-10T07:45:00').
    """
    from .events.watcher import get_registry
    from .events.sources.alarm_watcher import make_alarm_watcher
    from .database import save_watcher as _save_watcher, transaction
    from datetime import datetime as _dt, timezone as _tz
    try:
        _fire_dt = _dt.fromisoformat(fire_at)
        if _fire_dt.tzinfo is None:
            _fire_dt = _fire_dt.astimezone()
        if (_fire_dt - _dt.now(_tz.utc)).total_seconds() < 0:
            return {"error": f"fire_at '{fire_at}' is in the past. Call get_datetime first to get the current time, then construct a future fire_at."}
        watcher = make_alarm_watcher(message, fire_at)
        registry = get_registry()
        registry.register(watcher)
        registry._start_watcher(watcher)
        conn = shared_connection()
        with transaction(conn):
            _save_watcher(conn, watcher.id, watcher.source_type, watcher.name, watcher.description, watcher.fire_at)
        return {"ok": True, "watcher_id": watcher.id, "message": message, "fire_at": watcher.fire_at}
    except Exception as exc:
        return {"error": str(exc)}


@mcp.tool()
def react_to_message(message_id: str, emoji: str) -> dict:
    """
    Add an emoji reaction to a message in the conversation.
    Use this when something genuinely resonates — something funny, insightful, or worth
    acknowledging. Use sparingly and naturally; react-and-reply is fine, but reactions
    should never replace a reply.

    Args:
        message_id: The ID of the message to react to.
        emoji:      A single emoji character (e.g. "👍", "😂", "🔥").
    """
    import uuid
    from .database import add_reaction, transaction
    conn = shared_connection()
    msg_row = conn.execute("SELECT id FROM messages WHERE id = ?", (message_id,)).fetchone()
    if not msg_row:
        return {"error": f"Message {message_id} not found"}
    with transaction(conn):
        row = add_reaction(conn, str(uuid.uuid4()), message_id, "assistant", emoji)
    return dict(row)
