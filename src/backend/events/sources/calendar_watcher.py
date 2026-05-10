"""
Calendar reminder watcher — polls Google Calendar for events starting in
the next `lookahead_minutes` minutes and fires a reminder if one is found
that hasn't been announced yet.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from ...database import shared_connection
from ...tools.google import get_credentials
from ..watcher import EventItem, Watcher, make_watcher_id

# IDs of events already announced this session (resets on restart)
_announced: set[str] = set()

LOOKAHEAD_MINUTES = 30


async def _poll(watcher: Watcher, queue: asyncio.Queue) -> None:
    conn = shared_connection()
    creds = get_credentials(conn)
    if not creds:
        return  # Google not connected — silently skip

    from googleapiclient.discovery import build  # type: ignore
    from googleapiclient.errors import HttpError  # type: ignore

    now = datetime.now(timezone.utc)
    time_min = now.isoformat()
    time_max = (now + timedelta(minutes=LOOKAHEAD_MINUTES)).isoformat()

    try:
        service = build("calendar", "v3", credentials=creds)
        result = service.events().list(
            calendarId="primary",
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy="startTime",
            maxResults=10,
        ).execute()
    except HttpError:
        return

    for event in result.get("items", []):
        event_id = event.get("id", "")
        if event_id in _announced:
            continue
        summary = event.get("summary", "(no title)")
        start = event.get("start", {})
        start_str = start.get("dateTime") or start.get("date", "")
        location = event.get("location", "")
        description = event.get("description", "")

        body = f'Your calendar event **"{summary}"** starts in about {LOOKAHEAD_MINUTES} minutes.'
        if location:
            body += f" Location: {location}."
        if description:
            body += f" Notes: {description[:200]}."

        _announced.add(event_id)
        await queue.put(EventItem(
            id=make_watcher_id(),
            watcher_id=watcher.id,
            watcher_name=watcher.name,
            title=f"Upcoming: {summary}",
            body=body,
        ))


def make_calendar_watcher() -> Watcher:
    return Watcher(
        id=make_watcher_id(),
        name="Calendar reminders",
        description=f"Fires a reminder when a calendar event starts within {LOOKAHEAD_MINUTES} minutes.",
        source_type="calendar",
        interval_seconds=120,  # poll every 2 minutes
        _poll_fn=_poll,
    )
