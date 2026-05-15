"""Run an AI CLI provider, persist normalized events, and fan out to subscribers."""

from __future__ import annotations

import asyncio
import shutil
from typing import Any, AsyncIterator, Awaitable, Callable

from . import db, projects
from .providers import AgentRuntime, get_provider

EventCallback = Callable[[dict[str, Any]], Awaitable[None]]


class RunHandle:
    """Tracks a single in-flight provider run for one project."""

    def __init__(self, project_id: str, run_id: int, provider: AgentRuntime) -> None:
        self.project_id = project_id
        self.run_id = run_id
        self.provider = provider
        # Kept for backwards compatibility but no longer the source of truth;
        # all events fan out via the project-level subscribers map below.
        self.subscribers: set[EventCallback] = set()
        self.done = asyncio.Event()
        self.exit_code: int | None = None
        self.proc: asyncio.subprocess.Process | None = None
        self.cancelled = False

    async def fanout(self, event: dict[str, Any]) -> None:
        # Fan out to project-level subscribers (so a WS connection that opened
        # before this run started still receives events) and also to any
        # legacy per-handle subscribers.
        targets = set(_project_subscribers.get(self.project_id, set()))
        targets.update(self.subscribers)
        for cb in list(targets):
            try:
                await cb(event)
            except Exception:
                # Drop bad subscribers from whichever set held them.
                _project_subscribers.get(self.project_id, set()).discard(cb)
                self.subscribers.discard(cb)

    async def cancel(self) -> None:
        """Interrupt the running provider subprocess.

        Tries SIGTERM first to let the CLI flush state; escalates to SIGKILL
        after 3s. Safe to call multiple times.
        """
        self.cancelled = True
        proc = self.proc
        if proc is None or proc.returncode is not None:
            return
        try:
            proc.terminate()
        except ProcessLookupError:
            return
        try:
            await asyncio.wait_for(proc.wait(), timeout=3)
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except ProcessLookupError:
                pass


# project_id → RunHandle (one run per project at a time)
_active: dict[str, RunHandle] = {}
_locks: dict[str, asyncio.Lock] = {}

# project_id → callbacks for *all* runs of that project. WS connections
# subscribe here once on connect; they keep receiving events even when the
# specific RunHandle that triggered them is recreated for the next run.
_project_subscribers: dict[str, set[EventCallback]] = {}


def subscribe(project_id: str, cb: EventCallback) -> None:
    _project_subscribers.setdefault(project_id, set()).add(cb)


def unsubscribe(project_id: str, cb: EventCallback) -> None:
    s = _project_subscribers.get(project_id)
    if s:
        s.discard(cb)
        if not s:
            _project_subscribers.pop(project_id, None)


def _lock_for(project_id: str) -> asyncio.Lock:
    if project_id not in _locks:
        _locks[project_id] = asyncio.Lock()
    return _locks[project_id]


def get_active(project_id: str) -> RunHandle | None:
    return _active.get(project_id)


async def start_run(
    project_id: str,
    user_message: str,
    provider_name: str | None = None,
) -> RunHandle:
    """Start a provider run for the project. Returns immediately with a RunHandle.

    Refuses to start if a run is already active for this project.
    """
    lock = _lock_for(project_id)
    async with lock:
        if project_id in _active:
            raise RuntimeError("a run is already active for this project")

        proj = await projects.get_project(project_id)
        if not proj:
            raise FileNotFoundError(f"project not found: {project_id}")

        workdir = projects.project_workdir(project_id)
        if not workdir.exists():
            raise FileNotFoundError(f"project workdir missing: {workdir}")

        provider = get_provider(provider_name)

        # Always sync the latest provider-specific prompts before each run.
        provider.prepare_workdir(workdir)

        run_id = await db.create_run(project_id, user_message)
        handle = RunHandle(project_id, run_id, provider)
        _active[project_id] = handle

    # Fire and forget — the actual subprocess loop runs in the background.
    asyncio.create_task(_run_loop(handle, user_message))
    return handle


async def _run_loop(handle: RunHandle, user_message: str) -> None:
    project_id = handle.project_id
    workdir = projects.project_workdir(project_id)
    provider = handle.provider
    # seq is project-wide and monotonic. Continue from the last persisted
    # seq so cross-run ordering (sort by seq) stays correct.
    seq = await db.get_max_seq(project_id)
    rc: int = -1

    async def _emit(event: dict[str, Any], *, persist: bool = True) -> None:
        nonlocal seq
        seq += 1
        event["seq"] = seq
        event["run_id"] = handle.run_id
        event.setdefault("provider", provider.name)
        if persist:
            await db.insert_message(project_id, handle.run_id, seq, event)
        await handle.fanout(event)

    async def _emit_many(events: list[dict[str, Any]], *, persist: bool = True) -> None:
        for event in events:
            if event.get("type") == "agent_batch":
                nested = event.get("events")
                if isinstance(nested, list):
                    await _emit_many(
                        [e for e in nested if isinstance(e, dict)],
                        persist=persist,
                    )
                continue
            await _emit(event, persist=persist)

    try:
        # Persist + broadcast the user's input as the first message of this
        # run, so the chat UI shows what the user actually said and so a
        # page-refresh replay still includes it.
        user_event = {
            "type": "user_input",
            "text": user_message,
            "provider": provider.name,
        }
        await _emit(user_event)

        command = provider.build_command(user_message, workdir)
        if not shutil.which(command.argv[0]):
            await _emit(
                {
                    "type": "agent_system",
                    "level": "error",
                    "message": provider.missing_binary_message(),
                }
            )
            rc = 127
            return

        proc = await asyncio.create_subprocess_exec(
            *command.argv,
            cwd=str(command.cwd),
            env=command.env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        handle.proc = proc

        async def _consume(stream: asyncio.StreamReader, channel: str) -> None:
            nonlocal seq
            async for raw in stream:
                line = raw.decode(errors="replace").rstrip("\n")
                if not line:
                    continue
                for parsed in provider.parse_line(line, channel):
                    await _emit_many([parsed.event], persist=parsed.persist)

        assert proc.stdout is not None and proc.stderr is not None
        await asyncio.gather(
            _consume(proc.stdout, "stdout"),
            _consume(proc.stderr, "stderr"),
        )
        rc = await proc.wait()

        # Auto git commit after every run.
        try:
            await projects.git_commit_run(
                project_id,
                f"run {handle.run_id}: {user_message[:60]}",
            )
        except Exception as e:
            await _emit(
                {
                    "type": "agent_system",
                    "level": "warning",
                    "message": f"git commit failed: {e}",
                }
            )

    except Exception as e:
        await _emit(
            {
                "type": "agent_system",
                "level": "error",
                "message": f"runner crashed: {e!r}",
            }
        )
        rc = -1

    finally:
        # Clear active state BEFORE telling the client the run is done,
        # otherwise the client may POST /runs again before we've released the slot.
        handle.exit_code = rc
        _active.pop(project_id, None)
        if handle.cancelled:
            try:
                await _emit(
                    {
                        "type": "agent_system",
                        "level": "warning",
                        "message": "Run 已被用户中断",
                    }
                )
            except Exception:
                pass
        try:
            await db.finish_run(handle.run_id, exit_code=rc)
        except Exception:
            pass
        try:
            await _emit({"type": "run_complete", "exit_code": rc})
        except Exception:
            pass
        handle.done.set()


async def replay_history(project_id: str, since_seq: int = 0) -> AsyncIterator[dict[str, Any]]:
    for row in await db.list_messages(project_id, since_seq=since_seq):
        msg = row["payload"]
        msg["seq"] = row["seq"]
        yield msg
