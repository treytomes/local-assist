"""
Scheduled check-in watcher — fires a periodic proactive check-in from Mara.
Default: once every 4 hours when the app is open.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from ..watcher import EventItem, Watcher, make_watcher_id

CHECK_IN_INTERVAL = 4 * 60 * 60  # 4 hours in seconds


async def _poll(watcher: Watcher, queue: asyncio.Queue) -> None:
    now = datetime.now(timezone.utc)
    body = (
        f"It's {now.strftime('%H:%M UTC')} — checking in. "
        "Is there anything on your mind, or anything I can help with right now?"
    )
    await queue.put(EventItem(
        id=make_watcher_id(),
        watcher_id=watcher.id,
        watcher_name=watcher.name,
        title="Scheduled check-in",
        body=body,
    ))


def make_schedule_watcher() -> Watcher:
    return Watcher(
        id=make_watcher_id(),
        name="Scheduled check-ins",
        description="Periodic proactive check-in from Mara (every 4 hours).",
        source_type="schedule",
        interval_seconds=CHECK_IN_INTERVAL,
        enabled=False,  # off by default — user opts in
        _poll_fn=_poll,
    )
