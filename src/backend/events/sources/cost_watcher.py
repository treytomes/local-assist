"""
Cost threshold watcher — fires once when all-time spend crosses the configured alert threshold.
Resets (can fire again) after another full threshold increment is spent.
"""
from __future__ import annotations

import asyncio

from ..watcher import EventItem, Watcher, make_watcher_id


_last_fired_at: float | None = None  # threshold value at which we last fired


async def _poll(watcher: Watcher, queue: asyncio.Queue) -> None:
    global _last_fired_at
    from ...database import shared_connection, get_setting
    from ...cost import get_all_time_cost

    conn = shared_connection()
    raw = get_setting(conn, "cost_alert_threshold")
    if raw is None:
        return
    try:
        threshold = float(raw)
    except ValueError:
        return
    if threshold <= 0:
        return

    total = get_all_time_cost(conn)

    # Fire when we cross a new threshold multiple (0→1×, 1×→2×, etc.)
    current_multiple = int(total / threshold)
    last_multiple = int(_last_fired_at / threshold) if _last_fired_at is not None else -1

    if current_multiple > last_multiple and total >= threshold:
        _last_fired_at = total
        await queue.put(EventItem(
            id=make_watcher_id(),
            watcher_id=watcher.id,
            watcher_name=watcher.name,
            title="Spend threshold reached",
            body=(
                f"All-time spend has reached ${total:.4f}, "
                f"crossing the ${threshold:.2f} alert threshold. "
                f"Check the Cost Dashboard for a breakdown."
            ),
        ))


def make_cost_watcher() -> Watcher:
    return Watcher(
        id=make_watcher_id(),
        name="Spend threshold alert",
        description="Fires when all-time cost crosses the configured alert threshold.",
        source_type="cost",
        interval_seconds=300,  # poll every 5 minutes
        _poll_fn=_poll,
    )
