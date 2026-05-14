"""Project lifecycle: create workdir, copy latest prompts, git init, list/get/delete."""

from __future__ import annotations

import asyncio
import re
import shutil
import uuid
from pathlib import Path
from typing import Any

from . import db

BACKEND_DIR = Path(__file__).parent
PROMPTS_DIR = BACKEND_DIR / "prompts"
PROJECTS_DIR = BACKEND_DIR.parent / "projects"

PHASE_FILES = [
    "01_requirements.md",
    "02_architecture.md",
    "03_components.md",
    "04_circuit_design.md",
    "05_netlist.md",
    "06_review.md",
    "07_change_log.md",
    "final_report.md",
]


def project_workdir(project_id: str) -> Path:
    return PROJECTS_DIR / project_id


def _slugify(name: str) -> str:
    """Force ASCII-only slug. Non-ASCII chars (Chinese etc.) are dropped.

    Project name remains in its original form in the DB (for UI display),
    only the on-disk ID gets sanitized.
    """
    s = re.sub(r"[^A-Za-z0-9_-]+", "-", name.strip())
    s = s.strip("-")[:40]
    return s or "project"


async def _run(*cmd: str, cwd: Path) -> tuple[int, str]:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    stdout, _ = await proc.communicate()
    return proc.returncode or 0, stdout.decode(errors="replace")


def sync_prompts(workdir: Path) -> None:
    """Copy latest orchestrator + subagents into the project workdir.

    Called every time a run starts, so the latest prompt versions are always used.
    """
    shutil.copy(PROMPTS_DIR / "orchestrator.md", workdir / "CLAUDE.md")
    agents_dst = workdir / ".claude" / "agents"
    agents_dst.mkdir(parents=True, exist_ok=True)
    for f in (PROMPTS_DIR / "agents").glob("*.md"):
        shutil.copy(f, agents_dst / f.name)


async def create_project(name: str) -> dict[str, Any]:
    project_id = f"{_slugify(name)}-{uuid.uuid4().hex[:8]}"
    workdir = project_workdir(project_id)
    if workdir.exists():
        raise FileExistsError(f"workdir already exists: {workdir}")
    workdir.mkdir(parents=True)

    sync_prompts(workdir)

    # Empty placeholder phase files so the watcher and UI can list them upfront.
    for fname in PHASE_FILES:
        (workdir / fname).touch()

    # git init + initial commit
    await _run("git", "init", "-q", cwd=workdir)
    await _run("git", "config", "user.email", "pcb-system@local", cwd=workdir)
    await _run("git", "config", "user.name", "pcb-system", cwd=workdir)
    await _run("git", "add", "-A", cwd=workdir)
    await _run("git", "commit", "-q", "-m", "init: scaffold project", cwd=workdir)

    return await db.insert_project(project_id, name)


async def list_projects() -> list[dict[str, Any]]:
    return await db.list_projects()


async def get_project(project_id: str) -> dict[str, Any] | None:
    return await db.get_project(project_id)


async def delete_project(project_id: str) -> bool:
    workdir = project_workdir(project_id)
    if workdir.exists():
        shutil.rmtree(workdir)
    return await db.delete_project(project_id)


async def list_files(project_id: str) -> list[dict[str, Any]]:
    workdir = project_workdir(project_id)
    if not workdir.exists():
        return []
    out: list[dict[str, Any]] = []
    for fname in ["00_project_brief.md", *PHASE_FILES]:
        p = workdir / fname
        if p.exists():
            stat = p.stat()
            out.append(
                {
                    "name": fname,
                    "size": stat.st_size,
                    "modified_at": stat.st_mtime,
                }
            )
    return out


async def read_file(project_id: str, fname: str) -> str | None:
    # Restrict reads to known files only (no path traversal).
    allowed = {"00_project_brief.md", "CLAUDE.md", *PHASE_FILES}
    if fname not in allowed:
        return None
    p = project_workdir(project_id) / fname
    if not p.exists():
        return None
    return p.read_text(encoding="utf-8")


async def git_commit_run(project_id: str, message: str) -> None:
    workdir = project_workdir(project_id)
    if not workdir.exists():
        return
    rc, _ = await _run("git", "status", "--porcelain", cwd=workdir)
    # Always attempt commit; if nothing changed it just returns nonzero.
    await _run("git", "add", "-A", cwd=workdir)
    await _run("git", "commit", "-q", "--allow-empty", "-m", message, cwd=workdir)
