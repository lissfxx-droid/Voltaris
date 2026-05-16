// useProjectSocket: opens one WS per opened project, accumulates state.
//
// Maintains:
//   - chat: ChatItem[]              (assistant text, tool_use+result, system events)
//   - files: Map<path, content>     (latest content for each markdown file)
//   - runActive: boolean            (true between run start and run_complete)
//   - connected: boolean
//
// State is rebuilt from history replay + live events, no extra HTTP calls needed.

import { useEffect, useRef, useState } from "react";

import { api } from "./api";
import type {
  AgentMessage,
  AgentProvider,
  AgentResult,
  AgentSession,
  AgentSystem,
  AgentTool,
  ChatItem,
  ChatToolUseItem,
  RawLine,
  WSMessage,
} from "./types";

interface SocketState {
  chat: ChatItem[];
  files: Record<string, string>;
  runActive: boolean;
  connected: boolean;
  provider: AgentProvider | null;
  configuredProvider: AgentProvider | null;
  lastSeq: number;
  lastEvent: string | null;
  lastRunId: number | null;
  lastRunExitCode: number | null;
  // Becomes true after the WS handshake-complete `ws_ready` envelope arrives.
  // Events arriving before that are historical replays; events after are live.
  // We only let *live* events flip runActive=true, so replaying an old
  // `system/init` doesn't resurrect a long-dead run.
  replayDone: boolean;
}

const EMPTY: SocketState = {
  chat: [],
  files: {},
  runActive: false,
  connected: false,
  provider: null,
  configuredProvider: null,
  lastSeq: 0,
  lastEvent: null,
  lastRunId: null,
  lastRunExitCode: null,
  replayDone: false,
};

function displayName(provider?: AgentProvider | null): string {
  if (provider === "codex") return "Codex";
  if (provider === "claude") return "Claude";
  return "Agent";
}

function providerFrom(msg: WSMessage): AgentProvider | undefined {
  const provider = (msg as { provider?: unknown }).provider;
  return typeof provider === "string" ? provider : undefined;
}

function messageContent(msg: WSMessage): unknown[] {
  const message = (msg as { message?: unknown }).message;
  if (
    typeof message !== "object" ||
    message === null ||
    !Array.isArray((message as { content?: unknown }).content)
  ) {
    return [];
  }
  return (message as { content: unknown[] }).content;
}

function toolResultText(c: unknown): string {
  if (typeof c === "string") return c;
  if (!Array.isArray(c)) return JSON.stringify(c);
  return c
    .map((b) =>
      typeof b === "object" &&
      b !== null &&
      (b as { type?: unknown }).type === "text" &&
      typeof (b as { text?: unknown }).text === "string"
        ? (b as { text: string }).text
        : JSON.stringify(b),
    )
    .join("\n");
}

function applyEvent(state: SocketState, msg: WSMessage): SocketState {
  // Track seq watermark so we can resume on reconnect.
  const seqRaw = (msg as { seq?: number }).seq;
  const seq = typeof seqRaw === "number" ? seqRaw : state.lastSeq;
  const next: SocketState = { ...state, lastSeq: Math.max(state.lastSeq, seq) };

  switch (msg.type) {
    case "ws_ready":
      // Everything from here on is live. Replayed events before this point
      // could not flip runActive=true.
      next.replayDone = true;
      next.lastEvent = "WebSocket ready";
      return next;

    case "file_updated": {
      const m = msg as Extract<WSMessage, { type: "file_updated" }>;
      next.files = { ...next.files, [m.path]: m.content };
      next.lastEvent = `Updated ${m.path}`;
      return next;
    }

    case "file_deleted": {
      const m = msg as Extract<WSMessage, { type: "file_deleted" }>;
      const { [m.path]: _, ...rest } = next.files;
      next.files = rest;
      next.lastEvent = `Deleted ${m.path}`;
      return next;
    }

    case "user_input": {
      // The user's prompt to start a run, broadcast by the backend so the
      // chat shows what the user actually said (and survives a refresh).
      const m = msg as { type: "user_input"; text: string };
      next.chat = [
        ...next.chat,
        {
          kind: "user",
          id: `usr-${seq}`,
          text: m.text,
        },
      ];
      next.lastEvent = "User input received";
      return next;
    }

    case "agent_session": {
      const m = msg as AgentSession;
      next.provider = m.provider;
      if (next.replayDone) {
        next.runActive = true;
        next.lastRunExitCode = null;
      }
      next.lastEvent = `${m.provider_display || displayName(m.provider)} session started`;
      next.chat = [
        ...next.chat,
        {
          kind: "system",
          id: `sys-${seq}`,
          level: "info",
          text: `${m.provider_display || displayName(m.provider)} session started${
            m.session_id ? ` (${m.session_id.slice(0, 8)})` : ""
          }`,
        },
      ];
      return next;
    }

    case "agent_message": {
      const m = msg as AgentMessage;
      next.chat = [
        ...next.chat,
        {
          kind: "text",
          id: `a-${seq}`,
          role: "assistant",
          provider: m.provider || providerFrom(msg) || next.provider || undefined,
          text: m.text,
        },
      ];
      next.lastEvent = `${displayName(m.provider || providerFrom(msg) || next.provider)} message`;
      return next;
    }

    case "agent_tool": {
      const m = msg as AgentTool;
      if (m.phase === "started") {
        next.chat = [
          ...next.chat,
          {
            kind: "tool_use",
            id: m.tool_id,
            name: m.name || "tool",
            input: m.input ?? {},
            provider: m.provider || providerFrom(msg) || next.provider || undefined,
          },
        ];
        next.lastEvent = `${m.name || "tool"} started`;
      } else {
        next.chat = next.chat.map((it) =>
          it.kind === "tool_use" && (it as ChatToolUseItem).id === m.tool_id
            ? {
                ...it,
                result: m.result ?? "",
                isError: !!m.is_error,
                provider: m.provider || (it as ChatToolUseItem).provider,
              }
            : it,
        );
        next.lastEvent = `${m.name || "tool"} ${m.is_error ? "failed" : "finished"}`;
      }
      return next;
    }

    case "agent_result": {
      // End-of-run summary from the provider. Show as a styled card (rendered as
      // markdown by ChatPanel) so the formatted final summary is readable.
      const m = msg as AgentResult;
      if (m.text) {
        next.chat = [
          ...next.chat,
          {
            kind: "system",
            id: `result-${seq}`,
            level: m.is_error ? "error" : "success",
            text: m.text,
          },
        ];
      }
      next.lastEvent = m.is_error ? "Run result error" : "Run result ready";
      return next;
    }

    case "run_complete": {
      const m = msg as Extract<WSMessage, { type: "run_complete" }>;
      next.runActive = false;
      next.lastRunId = m.run_id;
      next.lastRunExitCode = m.exit_code;
      next.lastEvent = m.exit_code === 0 ? `Run #${m.run_id} completed` : `Run #${m.run_id} failed`;
      next.chat = [
        ...next.chat,
        {
          kind: "system",
          id: `done-${seq}`,
          level: m.exit_code === 0 ? "success" : "error",
          text:
            m.exit_code === 0
              ? `Run #${m.run_id} 完成`
              : `Run #${m.run_id} 异常退出 (exit ${m.exit_code})`,
        },
      ];
      return next;
    }

    case "agent_system": {
      const m = msg as AgentSystem;
      next.chat = [
        ...next.chat,
        {
          kind: "system",
          id: `s-${seq}`,
          level: m.level,
          text: m.message,
        },
      ];
      next.lastEvent = m.message;
      return next;
    }

    // Backward compatibility for messages persisted before provider
    // normalization was introduced.
    case "system_error":
    case "system_warning": {
      const m = msg as { type: string; message: string };
      next.chat = [
        ...next.chat,
        {
          kind: "system",
          id: `s-${seq}`,
          level: msg.type === "system_error" ? "error" : "warning",
          text: m.message,
        },
      ];
      next.lastEvent = m.message;
      return next;
    }

    case "system": {
      const m = msg as { type: "system"; subtype?: string; session_id?: string };
      if (m.subtype === "init") {
        if (next.replayDone) {
          next.runActive = true;
          next.lastRunExitCode = null;
        }
        next.provider = "claude";
        next.lastEvent = "Claude session started";
        next.chat = [
          ...next.chat,
          {
            kind: "system",
            id: `sys-${seq}`,
            level: "info",
            text: `Claude session started${m.session_id ? ` (${m.session_id.slice(0, 8)})` : ""}`,
          },
        ];
      }
      return next;
    }

    case "result": {
      const m = msg as { type: "result"; result?: string; is_error?: boolean };
      if (m.result) {
        next.chat = [
          ...next.chat,
          {
            kind: "system",
            id: `result-${seq}`,
            level: m.is_error ? "error" : "success",
            text: m.result,
          },
        ];
      }
      next.lastEvent = m.is_error ? "Run result error" : "Run result ready";
      return next;
    }

    case "agent_raw": {
      // Provider lines that the normalizer didn't recognize. Surface them as
      // info-level system entries so anything that slips through the Codex
      // event taxonomy is still visible in the timeline instead of being
      // silently dropped (the cause of the empty Codex step view).
      const m = msg as RawLine;
      const text = m.text ? `[${m.channel}] ${m.text}` : `[${m.channel}]`;
      next.chat = [
        ...next.chat,
        {
          kind: "system",
          id: `raw-${seq}`,
          level: "info",
          text,
        },
      ];
      next.lastEvent = `${m.channel} raw line`;
      return next;
    }
  }

  if (msg.type === "assistant" && typeof (msg as { message?: unknown }).message === "object") {
    const content = messageContent(msg);
    const newItems: ChatItem[] = [];
    for (const [i, block] of content.entries()) {
      const b = block as { type?: string; text?: string; id?: string; name?: string; input?: Record<string, unknown> };
      if (b.type === "text" && typeof b.text === "string") {
        newItems.push({
          kind: "text",
          id: `a-${seq}-${i}`,
          role: "assistant",
          provider: "claude",
          text: b.text,
        });
      } else if (b.type === "tool_use") {
        newItems.push({
          kind: "tool_use",
          id: b.id || `tool-${seq}-${i}`,
          name: b.name || "tool",
          input: b.input ?? {},
          provider: "claude",
        });
      }
      // skip "thinking" by default; could surface as collapsed card
    }
    next.chat = [...next.chat, ...newItems];
    if (newItems.length > 0) {
      next.lastEvent = "Claude stream update";
    }
    return next;
  }

  if (msg.type === "user" && typeof (msg as { message?: unknown }).message === "object") {
    // Match tool_results back to existing tool_use cards by tool_use_id.
    const content = messageContent(msg);
    let chat = next.chat;
    for (const block of content) {
      const b = block as { type?: string; tool_use_id?: string; content?: unknown; is_error?: boolean };
      if (b.type === "tool_result") {
        const text = toolResultText(b.content);
        chat = chat.map((it) =>
          it.kind === "tool_use" && (it as ChatToolUseItem).id === b.tool_use_id
            ? { ...it, result: text, isError: !!b.is_error }
            : it,
        );
      }
    }
    next.chat = chat;
    next.lastEvent = "Tool result received";
    return next;
  }

  return next;
}

export interface UseProjectSocket {
  state: SocketState;
  reset: () => void;
  setFileContent: (path: string, content: string) => void;
}

export function useProjectSocket(projectId: string | null): UseProjectSocket {
  const [state, setState] = useState<SocketState>(EMPTY);
  const stateRef = useRef(state);
  stateRef.current = state;

  useEffect(() => {
    if (!projectId) {
      setState(EMPTY);
      return;
    }
    setState(EMPTY);
    let closed = false;
    let ws: WebSocket | null = null;

    const open = () => {
      const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
      const since = stateRef.current.lastSeq;
      const url = `${proto}//${window.location.host}/ws/projects/${encodeURIComponent(
        projectId,
      )}?since=${since}`;
      ws = new WebSocket(url);

      ws.onopen = () => {
        setState((s) => ({ ...s, connected: true, lastEvent: "WebSocket connected" }));
        // The WS itself can't tell us authoritatively whether a run is in
        // progress (init events get replayed; we suppress those). Ask the
        // HTTP API for the canonical `active_run` flag and seed runActive.
        api
          .getProject(projectId)
          .then((p) => {
            setState((s) => ({
              ...s,
              runActive: p.active_run,
              provider: p.agent_provider,
              configuredProvider: p.agent_provider,
            }));
          })
          .catch(() => {
            /* project may have been deleted; ignore */
          });
      };
      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data) as WSMessage;
          setState((s) => applyEvent(s, msg));
        } catch {
          // Drop malformed frame.
        }
      };
      ws.onclose = () => {
        setState((s) => ({ ...s, connected: false, lastEvent: "WebSocket disconnected" }));
        if (!closed) {
          // Reconnect with backoff so dropped sockets resume.
          setTimeout(open, 2000);
        }
      };
      ws.onerror = () => {
        ws?.close();
      };
    };

    open();
    return () => {
      closed = true;
      ws?.close();
    };
  }, [projectId]);

  return {
    state,
    reset: () => setState(EMPTY),
    setFileContent: (path: string, content: string) => {
      setState((s) => ({
        ...s,
        files: { ...s.files, [path]: content },
        lastEvent: `Saved ${path}`,
      }));
    },
  };
}
