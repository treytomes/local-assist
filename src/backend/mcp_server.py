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
