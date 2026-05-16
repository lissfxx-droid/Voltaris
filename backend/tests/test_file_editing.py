from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException

from backend import db, main, projects


@pytest.mark.asyncio
async def test_write_file_is_limited_to_known_artifacts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "pcb.sqlite")
    monkeypatch.setattr(projects, "PROJECTS_DIR", tmp_path / "projects")

    await db.init_db()
    project = await projects.create_project("Editable")

    saved = await projects.write_file(project["id"], "01_requirements.md", "# Requirements\n")
    assert saved is not None
    assert saved["content"] == "# Requirements\n"
    assert await projects.read_file(project["id"], "01_requirements.md") == "# Requirements\n"

    yaml = await projects.write_file(project["id"], "05_circuit.thinir.yaml", "parts: []\n")
    assert yaml is not None
    assert await projects.read_file(project["id"], "05_circuit.thinir.yaml") == "parts: []\n"

    assert await projects.write_file(project["id"], "../escape.md", "nope") is None
    assert not (projects.project_workdir(project["id"]).parent / "escape.md").exists()


@pytest.mark.asyncio
async def test_put_file_rejects_active_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "pcb.sqlite")
    monkeypatch.setattr(projects, "PROJECTS_DIR", tmp_path / "projects")

    await db.init_db()
    project = await projects.create_project("Locked")

    monkeypatch.setattr(main.runner, "get_active", lambda _project_id: object())

    with pytest.raises(HTTPException) as exc:
        await main.put_file(
            project["id"],
            "01_requirements.md",
            main.SaveFileIn(content="# Locked\n"),
        )

    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_create_project_persists_agent_provider(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Runtime is now chosen at project creation and stored on the row, so
    # start_run can look it up and refuse to honour any client-side switch
    # (PCB-25 #4).
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "pcb.sqlite")
    monkeypatch.setattr(projects, "PROJECTS_DIR", tmp_path / "projects")

    await db.init_db()
    project = await projects.create_project("Pinned", agent_provider="codex")
    assert project["agent_provider"] == "codex"

    fetched = await projects.get_project(project["id"])
    assert fetched is not None
    assert fetched["agent_provider"] == "codex"

    listed = {row["id"]: row for row in await projects.list_projects()}
    assert listed[project["id"]]["agent_provider"] == "codex"


@pytest.mark.asyncio
async def test_create_project_rejects_unknown_provider(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "pcb.sqlite")
    monkeypatch.setattr(projects, "PROJECTS_DIR", tmp_path / "projects")

    await db.init_db()
    with pytest.raises(ValueError):
        await projects.create_project("Bad", agent_provider="not-a-runtime")

    # The aborted create must not leave a half-built workdir behind.
    listed = await projects.list_projects()
    assert listed == []


@pytest.mark.asyncio
async def test_get_project_detail_falls_back_to_env_default_for_legacy_rows(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Rows created before the agent_provider column existed (or by older
    # backends that didn't set it) should still report a usable provider so
    # the UI doesn't render an empty runtime badge.
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "pcb.sqlite")
    monkeypatch.setattr(projects, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setenv("VOLTARIS_AGENT_PROVIDER", "claude")

    await db.init_db()
    project = await projects.create_project("Legacy", agent_provider=None)

    detail = await main.get_project_detail(project["id"])
    assert detail["agent_provider"] == "claude"
