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
