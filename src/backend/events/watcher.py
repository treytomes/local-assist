"""
Watcher registry — tracks all active event sources and the shared event queue.

Each Watcher runs a periodic async poll. When it detects a noteworthy event
it appends an EventItem to the shared queue. The Mara response loop drains
the queue and generates AI replies.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine

log = logging.getLogger(__name__)


@dataclass
class EventItem:
    id: str
    watcher_id: str
    watcher_name: str
    title: str
    body: str
    fired_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    # If set, the Mara response loop will inject this into the named conversation;
    # otherwise a new "Notifications" conversation is created/reused.
    conversation_id: str | None = None


@dataclass
class Watcher:
    id: str
    name: str
    description: str
    source_type: str            # "calendar" | "system" | "schedule" | "alarm"
    interval_seconds: int
    enabled: bool = True
    one_shot: bool = False      # if True, deleted from registry after first fire
    fire_at: str | None = None  # ISO 8601 — used by alarm watchers instead of interval
    last_run: str | None = None
    last_error: str | None = None
    # The async poll function: (watcher, queue) -> None
    _poll_fn: Callable[["Watcher", asyncio.Queue], Coroutine[Any, Any, None]] | None = field(
        default=None, repr=False, compare=False
    )
    _task: asyncio.Task | None = field(default=None, repr=False, compare=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "source_type": self.source_type,
            "interval_seconds": self.interval_seconds,
            "enabled": self.enabled,
            "one_shot": self.one_shot,
            "fire_at": self.fire_at,
            "last_run": self.last_run,
            "last_error": self.last_error,
        }


class WatcherRegistry:
    def __init__(self) -> None:
        self._watchers: dict[str, Watcher] = {}
        self.queue: asyncio.Queue[EventItem] = asyncio.Queue()
        # Callbacks invoked with the watcher_id whenever a watcher is deleted
        self._on_delete: list[Callable[[str], None]] = []

    def add_delete_hook(self, fn: Callable[[str], None]) -> None:
        self._on_delete.append(fn)

    def register(self, watcher: Watcher) -> None:
        self._watchers[watcher.id] = watcher

    def all(self) -> list[Watcher]:
        return list(self._watchers.values())

    def get(self, watcher_id: str) -> Watcher | None:
        return self._watchers.get(watcher_id)

    def delete(self, watcher_id: str) -> bool:
        w = self._watchers.pop(watcher_id, None)
        if w and w._task and not w._task.done():
            w._task.cancel()
        if w is not None:
            for hook in self._on_delete:
                try:
                    hook(watcher_id)
                except Exception:
                    pass
        return w is not None

    def patch(self, watcher_id: str, enabled: bool | None = None, interval_seconds: int | None = None) -> Watcher | None:
        w = self._watchers.get(watcher_id)
        if not w:
            return None
        if enabled is not None:
            w.enabled = enabled
        if interval_seconds is not None:
            w.interval_seconds = interval_seconds
        return w

    def start_all(self) -> None:
        for w in self._watchers.values():
            self._start_watcher(w)

    def _start_watcher(self, w: Watcher) -> None:
        if w._poll_fn is None:
            return
        if w._task and not w._task.done():
            return

        registry_ref = self  # capture for one-shot deletion

        async def _loop():
            if w.fire_at:
                # Alarm watcher: sleep until the target time, then fire once
                try:
                    target = datetime.fromisoformat(w.fire_at)
                    if target.tzinfo is None:
                        target = target.astimezone()
                    delay = (target - datetime.now(timezone.utc)).total_seconds()
                    log.info("Alarm %s scheduled in %.1f seconds (fire_at=%s)", w.id, delay, w.fire_at)
                    if delay > 0:
                        await asyncio.sleep(delay)
                except Exception as exc:
                    log.error("Alarm %s sleep error: %s", w.id, exc)
                    registry_ref.delete(w.id)
                    return
                if not w.enabled:
                    log.info("Alarm %s skipped (disabled)", w.id)
                    registry_ref.delete(w.id)
                    return
                try:
                    await w._poll_fn(w, registry_ref.queue)
                    w.last_run = datetime.now(timezone.utc).isoformat()
                    w.last_error = None
                    log.info("Alarm %s fired: %s", w.id, w.description)
                except Exception as exc:
                    w.last_error = str(exc)
                    log.error("Alarm %s poll error: %s", w.id, exc)
                finally:
                    registry_ref.delete(w.id)
                return

            while True:
                await asyncio.sleep(w.interval_seconds)
                if not w.enabled:
                    continue
                try:
                    await w._poll_fn(w, registry_ref.queue)
                    w.last_run = datetime.now(timezone.utc).isoformat()
                    w.last_error = None
                except Exception as exc:
                    w.last_error = str(exc)
                if w.one_shot:
                    registry_ref.delete(w.id)
                    return

        w._task = asyncio.create_task(_loop())


# Module-level singleton set during lifespan
_registry: WatcherRegistry | None = None


def get_registry() -> WatcherRegistry:
    if _registry is None:
        raise RuntimeError("WatcherRegistry not initialised")
    return _registry


def set_registry(r: WatcherRegistry) -> None:
    global _registry
    _registry = r


def make_watcher_id() -> str:
    return str(uuid.uuid4())
