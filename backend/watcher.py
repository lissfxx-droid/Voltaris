"""Watch a project workdir and emit `file_updated` events for artifact changes."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Awaitable, Callable

from watchfiles import Change, awatch

from . import projects

EventCallback = Callable[[dict[str, Any]], Awaitable[None]]
WATCHED_SUFFIXES = {".md", ".yaml", ".yml"}

# project_id → (set of subscribers, watcher task)
_subs: dict[str, set[EventCallback]] = {}
_tasks: dict[str, asyncio.Task] = {}
_stop_events: dict[str, asyncio.Event] = {}


async def _watch_project(project_id: str) -> None:
    workdir = projects.project_workdir(project_id)
    stop = _stop_events[project_id]

    async for changes in awatch(str(workdir), stop_event=stop, recursive=False):
        for change_type, path_str in changes:
            p = Path(path_str)
            if p.suffix not in WATCHED_SUFFIXES:
                continue
            if change_type == Change.deleted:
                event = {"type": "file_deleted", "path": p.name}
            else:
                try:
                    content = p.read_text(encoding="utf-8")
                except (FileNotFoundError, OSError):
                    continue
                event = {
                    "type": "file_updated",
                    "path": p.name,
                    "content": content,
                }
            for cb in list(_subs.get(project_id, set())):
                try:
                    await cb(event)
                except Exception:
                    _subs.get(project_id, set()).discard(cb)


def subscribe(project_id: str, cb: EventCallback) -> None:
    """Subscribe to file events for a project. Lazily starts the watcher task."""
    if project_id not in _subs:
        _subs[project_id] = set()
        _stop_events[project_id] = asyncio.Event()
        _tasks[project_id] = asyncio.create_task(_watch_project(project_id))
    _subs[project_id].add(cb)


def unsubscribe(project_id: str, cb: EventCallback) -> None:
    if project_id not in _subs:
        return
    _subs[project_id].discard(cb)
    # If no subscribers left, stop the watcher to free the inotify handle.
    if not _subs[project_id]:
        _stop_events[project_id].set()
        _subs.pop(project_id, None)
        _tasks.pop(project_id, None)
        _stop_events.pop(project_id, None)
