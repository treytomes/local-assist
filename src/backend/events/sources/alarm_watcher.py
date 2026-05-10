"""
Alarm watcher — fires once at a specific datetime, then removes itself.
Created via the set_reminder tool.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from ..watcher import EventItem, Watcher, make_watcher_id


async def _poll(watcher: Watcher, queue: asyncio.Queue) -> None:
    await queue.put(EventItem(
        id=make_watcher_id(),
        watcher_id=watcher.id,
        watcher_name=watcher.name,
        title="Reminder",
        body=watcher.description,
    ))


def make_alarm_watcher(message: str, fire_at_iso: str, watcher_id: str | None = None) -> Watcher:
    """
    Create a one-shot alarm watcher that fires at fire_at_iso (ISO 8601).
    Pass watcher_id to reconstruct a persisted alarm with its original ID.

    Naive datetimes (no tzinfo) are treated as local time, not UTC, since
    that is what the user and model mean when they say "7:45 AM".
    """
    dt = datetime.fromisoformat(fire_at_iso)
    if dt.tzinfo is None:
        # Treat as local time — attach local timezone so delay calculation is correct
        dt = dt.astimezone()

    return Watcher(
        id=watcher_id or make_watcher_id(),
        name=f"Reminder: {message[:40]}",
        description=message,
        source_type="alarm",
        interval_seconds=0,
        one_shot=True,
        fire_at=dt.isoformat(),
        _poll_fn=_poll,
    )
