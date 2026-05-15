from __future__ import annotations

import os
from pathlib import Path

import pytest

from backend import db, projects, runner


@pytest.mark.asyncio
async def test_codex_provider_run_persists_normalized_events_and_commits(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_bin = tmp_path / "fake-codex"
    fake_bin.write_text(
        "#!/usr/bin/env sh\n"
        "printf '%s\\n' '{\"type\":\"event_msg\",\"msg\":{\"type\":\"session_configured\",\"session_id\":\"fake-session\"}}'\n"
        "printf '%s\\n' '{\"type\":\"agent_message_delta\",\"delta\":\"done\"}'\n"
        "printf '%s\\n' '{\"type\":\"turn_completed\",\"last_agent_message\":\"final\"}'\n",
        encoding="utf-8",
    )
    fake_bin.chmod(0o755)

    db_path = tmp_path / "pcb.sqlite"
    projects_dir = tmp_path / "projects"
    monkeypatch.setattr(db, "DB_PATH", db_path)
    monkeypatch.setattr(projects, "PROJECTS_DIR", projects_dir)
    monkeypatch.setenv("VOLTARIS_AGENT_PROVIDER", "codex")
    monkeypatch.setenv("CODEX_BIN", str(fake_bin))
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")

    await db.init_db()
    project = await projects.create_project("Smoke")
    handle = await runner.start_run(project["id"], "make a tiny board")
    await handle.done.wait()

    rows = await db.list_messages(project["id"])
    payloads = [row["payload"] for row in rows]

    assert handle.exit_code == 0
    assert [payload["type"] for payload in payloads] == [
        "user_input",
        "agent_session",
        "agent_message",
        "agent_result",
        "run_complete",
    ]
    assert payloads[1]["provider"] == "codex"
    assert payloads[2]["text"] == "done"
    assert payloads[3]["text"] == "final"
    assert (projects.project_workdir(project["id"]) / "AGENTS.md").exists()

    rc, log = await projects._run("git", "log", "--oneline", "-1", cwd=projects.project_workdir(project["id"]))
    assert rc == 0
    assert f"run {handle.run_id}: make a tiny board" in log


@pytest.mark.asyncio
async def test_start_run_accepts_explicit_provider(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_bin = tmp_path / "fake-codex"
    fake_bin.write_text(
        "#!/usr/bin/env sh\n"
        "printf '%s\\n' '{\"type\":\"event_msg\",\"msg\":{\"type\":\"session_configured\",\"session_id\":\"fake-session\"}}'\n",
        encoding="utf-8",
    )
    fake_bin.chmod(0o755)

    db_path = tmp_path / "pcb.sqlite"
    projects_dir = tmp_path / "projects"
    monkeypatch.setattr(db, "DB_PATH", db_path)
    monkeypatch.setattr(projects, "PROJECTS_DIR", projects_dir)
    monkeypatch.setenv("VOLTARIS_AGENT_PROVIDER", "claude")
    monkeypatch.setenv("CODEX_BIN", str(fake_bin))
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")

    await db.init_db()
    project = await projects.create_project("Explicit Provider")
    handle = await runner.start_run(project["id"], "use codex", "codex")
    await handle.done.wait()

    assert handle.provider.name == "codex"
