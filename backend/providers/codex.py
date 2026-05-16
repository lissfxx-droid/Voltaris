"""Codex CLI execution provider."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

from .base import (
    AgentRuntime,
    ProviderCommand,
    ProviderStreamEvent,
    agent_message,
    agent_result,
    agent_session_start,
    agent_tool_finish,
    agent_tool_start,
    copy_env,
    raw_event,
    system_event,
)


class CodexProvider(AgentRuntime):
    name = "codex"
    display_name = "Codex CLI"

    def __init__(self) -> None:
        self.bin = os.environ.get("CODEX_BIN", "codex") or "codex"

    def prepare_workdir(self, workdir: Path) -> None:
        from .. import projects

        agents_dir = projects.PROMPTS_DIR / "agents"
        refs_dir = projects.PROMPTS_DIR / "refs"
        tools_dir = projects.BACKEND_DIR / "tools"
        codex_agents_dst = workdir / ".codex" / "agents"
        codex_refs_dst = workdir / ".codex" / "refs"
        codex_tools_dst = workdir / ".codex" / "tools"
        codex_agents_dst.mkdir(parents=True, exist_ok=True)
        codex_refs_dst.mkdir(parents=True, exist_ok=True)
        codex_tools_dst.mkdir(parents=True, exist_ok=True)

        for f in agents_dir.glob("*.md"):
            shutil.copy(f, codex_agents_dst / f.name)
        for f in refs_dir.glob("*"):
            if f.is_file():
                shutil.copy(f, codex_refs_dst / f.name)
        for f in tools_dir.glob("*.py"):
            shutil.copy(f, codex_tools_dst / f.name)

        orchestrator = (projects.PROMPTS_DIR / "orchestrator.md").read_text(
            encoding="utf-8"
        )
        (workdir / "AGENTS.md").write_text(
            _codex_agents_md(orchestrator, agents_dir),
            encoding="utf-8",
        )

    def build_command(self, prompt: str, workdir: Path) -> ProviderCommand:
        # `--ask-for-approval` was removed from `codex exec` in newer Codex CLI
        # builds (the flag still exists at the top level only). Pass the
        # approval policy via the always-supported `-c` TOML override so the
        # command works on both old and current Codex versions.
        argv = [
            self.bin,
            "exec",
            "--json",
            "--cd",
            str(workdir),
            "--sandbox",
            os.environ.get("CODEX_SANDBOX", "workspace-write"),
            "-c",
            f"approval_policy={os.environ.get('CODEX_APPROVAL_POLICY', 'never')}",
        ]
        if _env_flag("CODEX_BYPASS_SANDBOX", default=False):
            argv.append("--dangerously-bypass-approvals-and-sandbox")
        if _env_flag("CODEX_EPHEMERAL", default=True):
            argv.append("--ephemeral")
        model = os.environ.get("CODEX_MODEL")
        if model:
            argv.extend(["--model", model])
        profile = os.environ.get("CODEX_PROFILE")
        if profile:
            argv.extend(["--profile", profile])
        argv.append(prompt)
        return ProviderCommand(
            argv=argv,
            cwd=workdir,
            env=copy_env(
                [
                    "CODEX_HOME",
                    "OPENAI_API_KEY",
                    "PATH",
                    "HOME",
                    "USER",
                    "SHELL",
                ]
            ),
        )

    def parse_line(self, line: str, channel: str) -> list[ProviderStreamEvent]:
        if not line:
            return []
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            # Codex writes some startup warnings to stderr before JSON mode is
            # fully initialized. Keep them visible but normalized.
            level = "warning" if channel == "stderr" else "info"
            return [ProviderStreamEvent(system_event(level, line))]
        if not isinstance(payload, dict):
            return [ProviderStreamEvent(raw_event(channel, line))]
        return [
            ProviderStreamEvent(event)
            for event in _normalize_codex_event(payload, channel)
            if event is not None
        ]

    def missing_binary_message(self) -> str:
        return f"codex binary not found ({self.bin}). Set CODEX_BIN or install Codex CLI."


def _codex_agents_md(orchestrator: str, agents_dir: Path) -> str:
    agent_sections: list[str] = []
    for path in sorted(agents_dir.glob("*.md")):
        agent_sections.append(
            f"### {path.stem}\n\n"
            f"Source: `.codex/agents/{path.name}`\n\n"
            f"{path.read_text(encoding='utf-8')}"
        )
    joined_agents = "\n\n---\n\n".join(agent_sections)
    return (
        "# Voltaris Codex Runtime Instructions\n\n"
        "You are running inside a Voltaris project workdir. Follow the same "
        "7-phase PCB workflow used by the Claude runtime, but Codex CLI does "
        "not expose Claude Code's Agent tool protocol. When the orchestrator "
        "says to call a subagent, execute that subagent inline by reading the "
        "matching `.codex/agents/<subagent>.md` file, applying its role and "
        "constraints, writing only the subagent's expected output files, then "
        "returning to the orchestrator flow. Run one subagent at a time.\n\n"
        "Keep writes inside this project workdir. Do not read or modify files "
        "outside the project directory. Use the same phase files, brief state "
        "machine, and git commit expectations as the orchestrator below.\n\n"
        "Some legacy subagent prompts mention repo-root paths. In this Codex "
        "runtime, use these workdir-local equivalents instead:\n"
        "- `backend/prompts/refs/CircuitIR.md` -> `.codex/refs/CircuitIR.md`\n"
        "- `backend/prompts/refs/example.thinir.yaml` -> `.codex/refs/example.thinir.yaml`\n"
        "- `backend/tools/validate.py` -> `.codex/tools/validate.py`\n"
        "- `backend/tools/lcsc_lookup.py` -> `.codex/tools/lcsc_lookup.py`\n"
        "When running `lcsc_lookup.py`, set `JLCPARTS_DB` to the deployment's "
        "jlcparts cache path if it is not available at the tool default.\n\n"
        "## Orchestrator\n\n"
        f"{orchestrator}\n\n"
        "## Inline Subagent References\n\n"
        f"{joined_agents}\n"
    )


def _normalize_codex_event(
    payload: dict[str, Any], channel: str
) -> list[dict[str, Any] | None]:
    typ = _event_type(payload)
    data = _event_payload(payload)

    if typ in {"session_configured", "sessionConfigured", "session/configured"}:
        provider = CodexProvider()
        return [
            agent_session_start(
                provider,
                session_id=_first_str(
                    data, "session_id", "sessionId", "thread_id", "threadId"
                ),
                raw=payload,
            )
        ]

    if typ in {"turn_started", "codex_turn_started", "codexTurnStarted"}:
        return [system_event("info", "Codex turn started", raw=payload)]

    if typ in {
        "agent_message",
        "agent_message_delta",
        "agent_message_content_delta",
        "item/agentMessage/delta",
        "agent_message_content_delta",
        "agentMessage/delta",
    }:
        text = _first_str(data, "message", "text", "delta", "content", "output_text")
        return [agent_message(text, raw=payload)] if text else []

    if typ in {
        "agent_reasoning",
        "agent_reasoning_delta",
        "reasoning_content_delta",
        "item/reasoning/summaryTextDelta",
        "item/reasoning/textDelta",
    }:
        text = _first_str(data, "text", "delta", "summary_text")
        return [system_event("info", text, raw=payload)] if text else []

    if typ in {
        "exec_command_begin",
        "exec_command_start",
        "tool_call_begin",
        "command/exec",
        "item/commandExecution",
    }:
        tool_id = (
            _first_str(data, "call_id", "id", "tool_call_id", "item_id")
            or _stable_id(payload)
        )
        name = _first_str(data, "name", "tool_name") or "exec_command"
        command = _first_str(data, "command", "cmd", "input")
        input_obj: dict[str, Any] = {}
        if command:
            input_obj["command"] = command
        if isinstance(data.get("arguments"), dict):
            input_obj.update(data["arguments"])
        return [agent_tool_start(tool_id, name, input_obj, raw=payload)]

    if typ in {
        "exec_command_output_delta",
        "command/exec/outputDelta",
        "item/commandExecution/outputDelta",
    }:
        return []

    if typ in {
        "exec_command_end",
        "tool_call_end",
        "command/exec/completed",
        "item/commandExecution/completed",
    }:
        tool_id = (
            _first_str(data, "call_id", "id", "tool_call_id", "item_id")
            or _stable_id(payload)
        )
        result = (
            _first_str(
                data, "output", "stdout", "stderr", "aggregated_output", "text", "delta"
            )
            or ""
        )
        is_error = bool(data.get("is_error") or data.get("error")) or _exit_code(
            data
        ) not in (None, 0)
        return [agent_tool_finish(tool_id, result=result, is_error=is_error, raw=payload)]

    if typ in {"patch_apply_begin", "patch_apply_updated", "patchApply/updated"}:
        tool_id = _first_str(data, "call_id", "id", "item_id") or _stable_id(payload)
        return [agent_tool_start(tool_id, "apply_patch", _compact_dict(data), raw=payload)]

    if typ in {
        "turn_completed",
        "codex_turn_ended",
        "codexTurnEnded",
        "task_complete",
        "turn/completed",
    }:
        text = _first_str(
            data,
            "last_agent_message",
            "lastAgentMessage",
            "final_message",
            "finalResponse",
            "output",
            "message",
        ) or _content_text(data.get("last_message"))
        return (
            [agent_result(text, raw=payload)]
            if text
            else [system_event("info", "Codex turn completed", raw=payload)]
        )

    if typ in {"error", "turn_failed", "inference_failed", "turn/failed"}:
        message = _first_str(data, "message", "error", "reason") or json.dumps(
            data or payload, ensure_ascii=False
        )
        return [system_event("error", message, raw=payload)]

    # Some current Codex builds emit nested response items in JSON mode. Accept
    # those shapes without tying the frontend to them.
    nested_events = _normalize_codex_response_item(payload)
    if nested_events:
        return nested_events

    if channel == "stderr":
        return [system_event("warning", json.dumps(payload, ensure_ascii=False), raw=payload)]
    return [raw_event(channel, json.dumps(payload, ensure_ascii=False))]


def _normalize_codex_response_item(payload: dict[str, Any]) -> list[dict[str, Any]]:
    item = payload.get("item")
    if not isinstance(item, dict):
        item = payload
    item_type = _first_str(item, "type")
    if item_type in {"message", "agent_message"}:
        text = _content_text(item.get("content"))
        return [agent_message(text, raw=payload)] if text else []
    if item_type in {"function_call", "custom_tool_call", "local_shell_call"}:
        tool_id = _first_str(item, "call_id", "id") or _stable_id(payload)
        name = _first_str(item, "name", "tool_name") or item_type
        input_obj = _compact_dict(item)
        return [agent_tool_start(tool_id, name, input_obj, raw=payload)]
    if item_type in {"function_call_output", "custom_tool_call_output"}:
        tool_id = _first_str(item, "call_id", "id") or _stable_id(payload)
        return [
            agent_tool_finish(
                tool_id,
                result=_content_text(item.get("output")) or _content_text(item.get("content")),
                raw=payload,
            )
        ]
    return []


def _event_type(payload: dict[str, Any]) -> str | None:
    for key in ("type", "event", "event_name", "eventName"):
        value = payload.get(key)
        if isinstance(value, str):
            if value in {"event_msg", "eventMsg", "event"}:
                nested = _event_payload(payload)
                if nested is not payload:
                    return _event_type(nested)
            return value
    msg = payload.get("msg")
    if isinstance(msg, dict):
        return _event_type(msg)
    return None


def _event_payload(payload: dict[str, Any]) -> dict[str, Any]:
    for key in ("payload", "data", "msg", "params"):
        value = payload.get(key)
        if isinstance(value, dict):
            return value
    return payload


def _first_str(data: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            text = _content_text(value)
            if text:
                return text
    return None


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                for key in ("text", "output_text", "summary_text", "content"):
                    value = item.get(key)
                    if isinstance(value, str):
                        parts.append(value)
                        break
        return "\n".join(part for part in parts if part)
    if isinstance(content, dict):
        return _first_str(content, "text", "output_text", "summary_text", "content") or ""
    return ""


def _compact_dict(data: dict[str, Any]) -> dict[str, Any]:
    skip = {
        "type",
        "event",
        "event_name",
        "eventName",
        "payload",
        "data",
        "msg",
        "params",
    }
    return {k: v for k, v in data.items() if k not in skip and v is not None}


def _exit_code(data: dict[str, Any]) -> int | None:
    value = data.get("exit_code") or data.get("exitCode")
    return value if isinstance(value, int) else None


def _stable_id(payload: dict[str, Any]) -> str:
    return f"codex-{abs(hash(json.dumps(payload, sort_keys=True, default=str)))}"


def _env_flag(name: str, *, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}
