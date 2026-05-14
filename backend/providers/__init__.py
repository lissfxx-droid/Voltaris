"""Execution provider registry for AI CLI runtimes."""

from __future__ import annotations

import os

from .base import AgentEvent, AgentRuntime, ProviderCommand, ProviderStreamEvent
from .claude import ClaudeProvider
from .codex import CodexProvider

DEFAULT_PROVIDER = "claude"


def selected_provider_name() -> str:
    """Return the configured provider name.

    Environment-level selection keeps the current API shape stable while making
    the execution engine explicit and easy to control per deployment.
    """
    return (os.environ.get("VOLTARIS_AGENT_PROVIDER") or DEFAULT_PROVIDER).strip().lower()


def get_provider(name: str | None = None) -> AgentRuntime:
    provider_name = (name or selected_provider_name()).strip().lower()
    if provider_name == "claude":
        return ClaudeProvider()
    if provider_name == "codex":
        return CodexProvider()
    raise ValueError(
        f"unknown agent provider {provider_name!r}; expected 'claude' or 'codex'"
    )


__all__ = [
    "AgentEvent",
    "AgentRuntime",
    "ClaudeProvider",
    "CodexProvider",
    "ProviderCommand",
    "ProviderStreamEvent",
    "get_provider",
    "selected_provider_name",
]
