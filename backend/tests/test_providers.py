from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.providers import get_provider
from backend.providers.claude import ClaudeProvider
from backend.providers.codex import CodexProvider


def events(provider, payload: dict, channel: str = "stdout") -> list[dict]:
    line = json.dumps(payload)
    return [item.event for item in provider.parse_line(line, channel)]


def test_provider_selection(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VOLTARIS_AGENT_PROVIDER", "codex")
    assert get_provider().name == "codex"

    monkeypatch.setenv("VOLTARIS_AGENT_PROVIDER", "claude")
    assert get_provider().name == "claude"

    monkeypatch.setenv("VOLTARIS_AGENT_PROVIDER", "unknown")
    with pytest.raises(ValueError):
        get_provider()


def test_claude_events_normalize_to_internal_protocol() -> None:
    provider = ClaudeProvider()

    session = events(
        provider,
        {"type": "system", "subtype": "init", "session_id": "abcdef123456"},
    )[0]
    assert session["type"] == "agent_session"
    assert session["provider"] == "claude"
    assert session["session_id"] == "abcdef123456"

    batch = events(
        provider,
        {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "text", "text": "hello"},
                    {"type": "tool_use", "id": "tool-1", "name": "Read", "input": {"file": "a.md"}},
                ]
            },
        },
    )[0]
    assert batch["type"] == "agent_batch"
    assert [event["type"] for event in batch["events"]] == ["agent_message", "agent_tool"]
    assert batch["events"][0]["text"] == "hello"
    assert batch["events"][1]["tool_id"] == "tool-1"

    result = events(
        provider,
        {
            "type": "user",
            "message": {
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "tool-1",
                        "content": [{"type": "text", "text": "done"}],
                    }
                ]
            },
        },
    )[0]
    assert result["type"] == "agent_tool"
    assert result["phase"] == "finished"
    assert result["result"] == "done"


def test_claude_command_injects_is_sandbox_for_root_skip_permissions(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("CLAUDE_BIN", "claude-test")
    monkeypatch.delenv("CLAUDE_SKIP_PERMISSIONS", raising=False)
    monkeypatch.delenv("IS_SANDBOX", raising=False)

    command = ClaudeProvider().build_command("ping", tmp_path)

    assert "--dangerously-skip-permissions" in command.argv
    assert command.env is not None
    assert command.env.get("IS_SANDBOX") == "1"


def test_claude_command_preserves_parent_is_sandbox(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("CLAUDE_BIN", "claude-test")
    monkeypatch.setenv("IS_SANDBOX", "custom-value")

    command = ClaudeProvider().build_command("ping", tmp_path)

    assert command.env is not None
    assert command.env.get("IS_SANDBOX") == "custom-value"


def test_claude_command_skips_is_sandbox_when_permissions_required(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("CLAUDE_BIN", "claude-test")
    monkeypatch.setenv("CLAUDE_SKIP_PERMISSIONS", "false")
    monkeypatch.delenv("IS_SANDBOX", raising=False)

    command = ClaudeProvider().build_command("ping", tmp_path)

    assert "--dangerously-skip-permissions" not in command.argv
    assert command.env is not None
    assert "IS_SANDBOX" not in command.env


def test_codex_command_is_explicit_and_sandboxed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CODEX_BIN", "codex-test")
    monkeypatch.setenv("CODEX_MODEL", "gpt-test")
    monkeypatch.delenv("CODEX_BYPASS_SANDBOX", raising=False)

    command = CodexProvider().build_command("build a board", tmp_path)

    assert command.argv[:2] == ["codex-test", "exec"]
    assert "--json" in command.argv
    assert command.argv[command.argv.index("--cd") + 1] == str(tmp_path)
    assert command.argv[command.argv.index("--sandbox") + 1] == "workspace-write"
    assert "--ask-for-approval" not in command.argv
    assert "approval_policy=never" in command.argv
    assert command.argv[command.argv.index("approval_policy=never") - 1] == "-c"
    assert "--dangerously-bypass-approvals-and-sandbox" not in command.argv
    assert command.argv[-1] == "build a board"


def test_codex_events_normalize_to_internal_protocol() -> None:
    provider = CodexProvider()

    session = events(
        provider,
        {"type": "event_msg", "msg": {"type": "session_configured", "session_id": "sess-1"}},
    )[0]
    assert session["type"] == "agent_session"
    assert session["provider"] == "codex"
    assert session["session_id"] == "sess-1"

    message = events(
        provider,
        {"type": "agent_message_delta", "delta": "Phase 1 complete"},
    )[0]
    assert message["type"] == "agent_message"
    assert message["text"] == "Phase 1 complete"
    assert isinstance(message["raw"], dict)

    tool = events(
        provider,
        {
            "type": "exec_command_begin",
            "call_id": "call-1",
            "command": "git status",
        },
    )[0]
    assert tool["type"] == "agent_tool"
    assert tool["phase"] == "started"
    assert tool["input"] == {"command": "git status"}

    result = events(
        provider,
        {
            "type": "exec_command_end",
            "call_id": "call-1",
            "stdout": "clean",
            "exit_code": 0,
        },
    )[0]
    assert result["type"] == "agent_tool"
    assert result["phase"] == "finished"
    assert result["is_error"] is False


def test_codex_prepare_workdir_writes_agents_md(tmp_path: Path) -> None:
    CodexProvider().prepare_workdir(tmp_path)

    agents_md = tmp_path / "AGENTS.md"
    assert agents_md.exists()
    content = agents_md.read_text(encoding="utf-8")
    assert "Voltaris Codex Runtime Instructions" in content
    assert "## Orchestrator" in content
    assert "### requirement-analyzer" in content
    assert ".codex/refs/CircuitIR.md" in content
    assert ".codex/tools/validate.py" in content
    assert (tmp_path / ".codex" / "agents" / "requirement-analyzer.md").exists()
    assert (tmp_path / ".codex" / "refs" / "CircuitIR.md").exists()
    assert (tmp_path / ".codex" / "tools" / "validate.py").exists()


def test_claude_prepare_workdir_excludes_ancestor_claude_md(tmp_path: Path) -> None:
    poison = tmp_path / "poisoned-host"
    workdir = poison / "Voltaris" / "projects" / "led-abc"
    workdir.mkdir(parents=True)
    poison_claude = poison / "CLAUDE.md"
    poison_claude.write_text("# Other agent runtime", encoding="utf-8")
    poison_local = poison / "CLAUDE.local.md"
    poison_local.write_text("# Other agent local", encoding="utf-8")
    poison_dotclaude = poison / ".claude" / "CLAUDE.md"
    poison_dotclaude.parent.mkdir()
    poison_dotclaude.write_text("# Other agent dotdir", encoding="utf-8")

    ClaudeProvider().prepare_workdir(workdir)

    settings_path = workdir / ".claude" / "settings.local.json"
    assert settings_path.exists()
    excludes = json.loads(settings_path.read_text(encoding="utf-8"))[
        "claudeMdExcludes"
    ]
    assert str(poison_claude.resolve()) in excludes
    assert str(poison_local.resolve()) in excludes
    assert str(poison_dotclaude.resolve()) in excludes
    # The project's own CLAUDE.md must NOT be excluded — it is the orchestrator.
    assert str((workdir / "CLAUDE.md").resolve()) not in excludes
    # The orchestrator was still written.
    assert (workdir / "CLAUDE.md").read_text(encoding="utf-8").startswith(
        "# 你是 PCB 设计 Orchestrator"
    )


def test_claude_prepare_workdir_writes_excludes_when_no_ancestor_pollution(
    tmp_path: Path,
) -> None:
    workdir = tmp_path / "clean" / "led-clean"
    workdir.mkdir(parents=True)

    ClaudeProvider().prepare_workdir(workdir)

    settings_path = workdir / ".claude" / "settings.local.json"
    assert settings_path.exists()
    payload = json.loads(settings_path.read_text(encoding="utf-8"))
    assert "claudeMdExcludes" in payload
    assert isinstance(payload["claudeMdExcludes"], list)
    # Project's own CLAUDE.md is never excluded.
    assert str((workdir / "CLAUDE.md").resolve()) not in payload["claudeMdExcludes"]


def test_claude_prepare_workdir_preserves_existing_settings(tmp_path: Path) -> None:
    workdir = tmp_path / "with-prior-settings"
    (workdir / ".claude").mkdir(parents=True)
    settings_path = workdir / ".claude" / "settings.local.json"
    settings_path.write_text(
        json.dumps({"someUnrelatedKey": "keep-me"}),
        encoding="utf-8",
    )

    ClaudeProvider().prepare_workdir(workdir)

    payload = json.loads(settings_path.read_text(encoding="utf-8"))
    assert payload["someUnrelatedKey"] == "keep-me"
    assert "claudeMdExcludes" in payload
