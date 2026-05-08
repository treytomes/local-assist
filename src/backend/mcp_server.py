"""
MCP server mounted onto the existing FastAPI app.
Exposes tools that the chat endpoint can call on behalf of the model.
"""
from mcp.server.fastmcp import FastMCP
from .tools.datetime_tool import get_datetime as _get_datetime
from .tools.system_info_tool import get_system_info as _get_system_info

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
