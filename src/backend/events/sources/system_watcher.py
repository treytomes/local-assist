"""
System resource watcher — fires when CPU or RAM exceeds configured thresholds.
Throttled: won't re-fire the same alert within COOLDOWN_SECONDS.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import psutil

from ..watcher import EventItem, Watcher, make_watcher_id

CPU_THRESHOLD = 90.0    # percent
RAM_THRESHOLD = 90.0    # percent
COOLDOWN_SECONDS = 300  # 5 minutes between repeat alerts for the same resource

_last_fired: dict[str, datetime] = {}


def _cooled_down(key: str) -> bool:
    last = _last_fired.get(key)
    if last is None:
        return True
    return (datetime.now(timezone.utc) - last).total_seconds() >= COOLDOWN_SECONDS


async def _poll(watcher: Watcher, queue: asyncio.Queue) -> None:
    cpu = psutil.cpu_percent(interval=1)
    ram = psutil.virtual_memory().percent

    if cpu >= CPU_THRESHOLD and _cooled_down("cpu"):
        _last_fired["cpu"] = datetime.now(timezone.utc)
        await queue.put(EventItem(
            id=make_watcher_id(),
            watcher_id=watcher.id,
            watcher_name=watcher.name,
            title="High CPU usage",
            body=f"CPU usage is at {cpu:.0f}% — above the {CPU_THRESHOLD:.0f}% threshold.",
        ))

    if ram >= RAM_THRESHOLD and _cooled_down("ram"):
        _last_fired["ram"] = datetime.now(timezone.utc)
        ram_info = psutil.virtual_memory()
        used_gb = ram_info.used / 1024 ** 3
        total_gb = ram_info.total / 1024 ** 3
        await queue.put(EventItem(
            id=make_watcher_id(),
            watcher_id=watcher.id,
            watcher_name=watcher.name,
            title="High memory usage",
            body=f"RAM usage is at {ram:.0f}% ({used_gb:.1f} GB / {total_gb:.1f} GB) — above the {RAM_THRESHOLD:.0f}% threshold.",
        ))


def make_system_watcher() -> Watcher:
    return Watcher(
        id=make_watcher_id(),
        name="System resource monitor",
        description=f"Alerts when CPU ≥ {CPU_THRESHOLD:.0f}% or RAM ≥ {RAM_THRESHOLD:.0f}% (5-minute cooldown).",
        source_type="system",
        interval_seconds=60,
        _poll_fn=_poll,
    )
