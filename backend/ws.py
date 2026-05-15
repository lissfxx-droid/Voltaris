"""WebSocket routes — one socket per project, multiplexes run events + file events."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from . import projects, runner, watcher

router = APIRouter()


@router.websocket("/ws/projects/{project_id}")
async def project_socket(websocket: WebSocket, project_id: str, since: int = 0):
    """One socket per project. Streams:

    - replay history (messages with seq > `since`)
    - live run events (agent_message / agent_tool / agent_result / run_complete)
    - file events (file_updated / file_deleted)
    """
    proj = await projects.get_project(project_id)
    if not proj:
        await websocket.close(code=4404, reason="project not found")
        return

    await websocket.accept()
    send_lock = asyncio.Lock()

    async def _send(payload: dict[str, Any]) -> None:
        async with send_lock:
            await websocket.send_json(payload)

    # 1. Replay any messages the client missed.
    async for msg in runner.replay_history(project_id, since_seq=since):
        await _send(msg)

    # 2. Snapshot the current on-disk artifact files. The watcher only emits
    # `file_updated` for live changes (and never persists them), so a fresh
    # client would otherwise have no way to learn the current file state
    # after a page refresh. This snapshot is authoritative — it overrides
    # whatever the replayed history contained.
    workdir = projects.project_workdir(project_id)
    if workdir.exists():
        for fname in projects.ARTIFACT_FILES:
            p = workdir / fname
            if not p.exists():
                continue
            try:
                content = p.read_text(encoding="utf-8")
            except OSError:
                continue
            await _send(
                {"type": "file_updated", "path": p.name, "content": content}
            )

    # 3. Subscribe to live events.
    # Subscribe at the project level so the same WS keeps receiving events
    # across multiple provider runs (each run creates a new RunHandle, but
    # project-level subscription persists).
    runner.subscribe(project_id, _send)
    watcher.subscribe(project_id, _send)

    await _send({"type": "ws_ready", "since": since})

    try:
        while True:
            # We don't expect inbound messages on this channel; reads only
            # serve to detect disconnects.
            try:
                await websocket.receive_text()
            except WebSocketDisconnect:
                break
    finally:
        watcher.unsubscribe(project_id, _send)
        runner.unsubscribe(project_id, _send)
