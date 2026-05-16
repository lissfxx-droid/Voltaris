"""Claude Code execution provider."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

from .base import (
    AgentEvent,
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


class ClaudeProvider(AgentRuntime):
    name = "claude"
    display_name = "Claude Code"

    def __init__(self) -> None:
        self.bin = os.environ.get("CLAUDE_BIN", "claude") or "claude"

    def prepare_workdir(self, workdir: Path) -> None:
        from .. import projects

        shutil.copy(projects.PROMPTS_DIR / "orchestrator.md", workdir / "CLAUDE.md")
        agents_dst = workdir / ".claude" / "agents"
        agents_dst.mkdir(parents=True, exist_ok=True)
        for f in (projects.PROMPTS_DIR / "agents").glob("*.md"):
            shutil.copy(f, agents_dst / f.name)

    def build_command(self, prompt: str, workdir: Path) -> ProviderCommand:
        argv = [
            self.bin,
            "-p",
            prompt,
            "--output-format",
            "stream-json",
            "--verbose",
        ]
        skip_permissions = _env_flag("CLAUDE_SKIP_PERMISSIONS", default=True)
        if skip_permissions:
            argv.append("--dangerously-skip-permissions")
        env = copy_env(
            [
                "ANTHROPIC_API_KEY",
                "CLAUDE_CODE_OAUTH_TOKEN",
                "IS_SANDBOX",
                "PATH",
                "HOME",
                "USER",
                "SHELL",
                "LANG",
                "LC_ALL",
            ]
        )
        # Claude CLI refuses --dangerously-skip-permissions under root unless
        # IS_SANDBOX=1 is set in its env. Backend services often run as root
        # (systemd, container, etc.) and copy_env() only forwards the explicit
        # allowlist, so any IS_SANDBOX from the parent shell would be stripped
        # without this. Force it on whenever we ask for permission bypass so the
        # behavior does not depend on however the backend was launched.
        if skip_permissions:
            env.setdefault("IS_SANDBOX", "1")
        return ProviderCommand(argv=argv, cwd=workdir, env=env)

    def parse_line(self, line: str, channel: str) -> list[ProviderStreamEvent]:
        if not line:
            return []
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            return [ProviderStreamEvent(raw_event(channel, line))]
        if not isinstance(payload, dict):
            return [ProviderStreamEvent(raw_event(channel, line))]
        return [ProviderStreamEvent(_normalize_claude_event(self, payload, channel))]

    def missing_binary_message(self) -> str:
        return (
            f"claude binary not found ({self.bin}). Set CLAUDE_BIN or install Claude Code."
        )


def _env_flag(name: str, *, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _normalize_claude_event(
    provider: ClaudeProvider, payload: dict[str, Any], channel: str
) -> AgentEvent:
    typ = payload.get("type")

    if typ == "system" and payload.get("subtype") == "init":
        return agent_session_start(
            provider,
            session_id=_as_str(payload.get("session_id")),
            raw=payload,
        )

    if typ == "assistant":
        content = _message_content(payload)
        events: list[AgentEvent] = []
        for block in content:
            if not isinstance(block, dict):
                continue
            block_type = block.get("type")
            if block_type == "text" and isinstance(block.get("text"), str):
                events.append(agent_message(block["text"], raw=payload))
            elif block_type == "tool_use":
                tool_id = _as_str(block.get("id")) or f"claude-tool-{id(block)}"
                name = _as_str(block.get("name")) or "tool"
                input_obj = (
                    block.get("input") if isinstance(block.get("input"), dict) else {}
                )
                events.append(agent_tool_start(tool_id, name, input_obj, raw=payload))
        if len(events) == 1:
            return events[0]
        if events:
            return {"type": "agent_batch", "events": events, "raw": payload}
        return system_event("info", "Claude assistant event received", raw=payload)

    if typ == "user":
        content = _message_content(payload)
        events: list[AgentEvent] = []
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_result":
                continue
            tool_id = _as_str(block.get("tool_use_id")) or "unknown"
            events.append(
                agent_tool_finish(
                    tool_id,
                    result=_tool_result_text(block.get("content")),
                    is_error=bool(block.get("is_error")),
                    raw=payload,
                )
            )
        if len(events) == 1:
            return events[0]
        if events:
            return {"type": "agent_batch", "events": events, "raw": payload}
        return system_event("info", "Claude user/tool-result event received", raw=payload)

    if typ == "result":
        text = _as_str(payload.get("result")) or _as_str(payload.get("error")) or ""
        if text:
            return agent_result(text, is_error=bool(payload.get("is_error")), raw=payload)
        return system_event("info", "Claude result received", raw=payload)

    if typ == "error":
        message = (
            _as_str(payload.get("message"))
            or _as_str(payload.get("error"))
            or line_safe(payload)
        )
        return system_event("error", message, raw=payload)

    if channel == "stderr":
        return system_event("warning", line_safe(payload), raw=payload)

    return {
        "type": "agent_raw",
        "channel": channel,
        "text": json.dumps(payload),
        "raw": payload,
    }


def _message_content(payload: dict[str, Any]) -> list[Any]:
    message = payload.get("message")
    if not isinstance(message, dict):
        return []
    content = message.get("content")
    return content if isinstance(content, list) else []


def _tool_result_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(_as_str(item.get("text")) or "")
            else:
                parts.append(json.dumps(item, ensure_ascii=False))
        return "\n".join(part for part in parts if part)
    return json.dumps(content, ensure_ascii=False)


def _as_str(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def line_safe(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)
