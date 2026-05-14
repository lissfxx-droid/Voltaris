"""Provider interface and normalized event helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


AgentEvent = dict[str, Any]


@dataclass(frozen=True)
class ProviderCommand:
    """Subprocess invocation prepared by a provider."""

    argv: list[str]
    cwd: Path
    env: dict[str, str] | None = None


@dataclass(frozen=True)
class ProviderStreamEvent:
    """Event parsed from one provider output line.

    `persist` lets providers suppress noisy stderr diagnostics while still
    allowing fatal errors to be shown through normalized system events.
    """

    event: AgentEvent
    persist: bool = True


class AgentRuntime(Protocol):
    name: str
    display_name: str

    def prepare_workdir(self, workdir: Path) -> None:
        """Sync provider-specific prompt files into the project workdir."""

    def build_command(self, prompt: str, workdir: Path) -> ProviderCommand:
        """Build the CLI command for this run."""

    def parse_line(self, line: str, channel: str) -> list[ProviderStreamEvent]:
        """Translate one stdout/stderr line into normalized internal events."""

    def missing_binary_message(self) -> str:
        """Human-readable setup error when the CLI binary is unavailable."""


def agent_session_start(
    provider: AgentRuntime,
    *,
    session_id: str | None = None,
    raw: dict[str, Any] | None = None,
) -> AgentEvent:
    event: AgentEvent = {
        "type": "agent_session",
        "phase": "started",
        "provider": provider.name,
        "provider_display": provider.display_name,
    }
    if session_id:
        event["session_id"] = session_id
    if raw is not None:
        event["raw"] = raw
    return event


def agent_message(text: str, *, raw: dict[str, Any] | None = None) -> AgentEvent:
    event: AgentEvent = {"type": "agent_message", "text": text}
    if raw is not None:
        event["raw"] = raw
    return event


def agent_tool_start(
    tool_id: str,
    name: str,
    input: dict[str, Any] | None = None,
    *,
    raw: dict[str, Any] | None = None,
) -> AgentEvent:
    event: AgentEvent = {
        "type": "agent_tool",
        "phase": "started",
        "tool_id": tool_id,
        "name": name,
        "input": input or {},
    }
    if raw is not None:
        event["raw"] = raw
    return event


def agent_tool_finish(
    tool_id: str,
    *,
    result: str = "",
    is_error: bool = False,
    raw: dict[str, Any] | None = None,
) -> AgentEvent:
    event: AgentEvent = {
        "type": "agent_tool",
        "phase": "finished",
        "tool_id": tool_id,
        "result": result,
        "is_error": is_error,
    }
    if raw is not None:
        event["raw"] = raw
    return event


def agent_result(
    text: str,
    *,
    is_error: bool = False,
    raw: dict[str, Any] | None = None,
) -> AgentEvent:
    event: AgentEvent = {
        "type": "agent_result",
        "text": text,
        "is_error": is_error,
    }
    if raw is not None:
        event["raw"] = raw
    return event


def system_event(
    level: str,
    message: str,
    *,
    raw: dict[str, Any] | None = None,
) -> AgentEvent:
    event: AgentEvent = {"type": "agent_system", "level": level, "message": message}
    if raw is not None:
        event["raw"] = raw
    return event


def raw_event(channel: str, text: str) -> AgentEvent:
    return {"type": "agent_raw", "channel": channel, "text": text}


def copy_env(allowlist: list[str]) -> dict[str, str]:
    """Copy only explicit environment variables into provider subprocesses."""
    import os

    return {key: os.environ[key] for key in allowlist if key in os.environ}
