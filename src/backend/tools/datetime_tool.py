from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import time


def get_datetime(timezone: str | None = None) -> dict:
    """
    Returns the current date, time, and timezone.
    If timezone is provided (IANA name e.g. "America/Chicago"), converts to that zone.
    Falls back to the system local timezone if timezone is None or invalid.
    """
    if timezone:
        try:
            tz = ZoneInfo(timezone)
        except (ZoneInfoNotFoundError, KeyError):
            tz = None
    else:
        tz = None

    now = datetime.now(tz=tz) if tz else datetime.now().astimezone()
    tz_name = now.tzname() or "Unknown"
    utc_offset = now.strftime("%z")  # e.g. "-0500"

    return {
        "iso": now.isoformat(),
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "timezone": tz_name,
        "utc_offset": utc_offset,
        "unix_timestamp": int(now.timestamp()),
    }
