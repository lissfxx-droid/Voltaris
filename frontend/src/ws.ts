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
  ChatItem,
  ChatToolUseItem,
  ClaudeAssistant,
  ClaudeContentBlock,
  ClaudeToolResult,
  ClaudeUser,
  WSMessage,
} from "./types";

interface SocketState {
  chat: ChatItem[];
  files: Record<string, string>;
  runActive: boolean;
  connected: boolean;
  lastSeq: number;
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
  lastSeq: 0,
  replayDone: false,
};

function isClaudeAssistant(m: WSMessage): m is ClaudeAssistant {
  return m.type === "assistant" && typeof (m as ClaudeAssistant).message === "object";
}

function isClaudeUser(m: WSMessage): m is ClaudeUser {
  return m.type === "user" && typeof (m as ClaudeUser).message === "object";
}

function toolResultText(c: ClaudeToolResult["content"]): string {
  if (typeof c === "string") return c;
  return c
    .map((b) => (b.type === "text" && b.text ? b.text : JSON.stringify(b)))
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
      return next;

    case "file_updated": {
      const m = msg as Extract<WSMessage, { type: "file_updated" }>;
      next.files = { ...next.files, [m.path]: m.content };
      return next;
    }

    case "file_deleted": {
      const m = msg as Extract<WSMessage, { type: "file_deleted" }>;
      const { [m.path]: _, ...rest } = next.files;
      next.files = rest;
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
      return next;
    }

    case "system": {
      // Claude session init / final result envelopes — we surface init only.
      const m = msg as { type: "system"; subtype?: string; session_id?: string };
      if (m.subtype === "init") {
        // Only flip runActive=true for *live* events. A replayed init from
        // a long-dead run would otherwise resurrect runActive forever (its
        // matching run_complete is also replayed, but later message ordering
        // can leave a stale active state).
        if (next.replayDone) {
          next.runActive = true;
        }
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
      // End-of-run summary from Claude. Show as a styled card (rendered as
      // markdown by ChatPanel) so the formatted final summary is readable.
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
      return next;
    }

    case "run_complete": {
      const m = msg as Extract<WSMessage, { type: "run_complete" }>;
      next.runActive = false;
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
      return next;
    }
  }

  if (isClaudeAssistant(msg)) {
    const newItems: ChatItem[] = [];
    for (const [i, block] of msg.message.content.entries()) {
      const b = block as ClaudeContentBlock;
      if (b.type === "text" && typeof (b as { text?: string }).text === "string") {
        newItems.push({
          kind: "text",
          id: `a-${seq}-${i}`,
          role: "assistant",
          text: (b as { text: string }).text,
        });
      } else if (b.type === "tool_use") {
        const tu = b as { id: string; name: string; input: Record<string, unknown> };
        newItems.push({
          kind: "tool_use",
          id: tu.id,
          name: tu.name,
          input: tu.input ?? {},
        });
      }
      // skip "thinking" by default; could surface as collapsed card
    }
    next.chat = [...next.chat, ...newItems];
    return next;
  }

  if (isClaudeUser(msg)) {
    // Match tool_results back to existing tool_use cards by tool_use_id.
    let chat = next.chat;
    for (const block of msg.message.content) {
      const b = block as ClaudeToolResult & { type: string };
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
    return next;
  }

  return next;
}

export interface UseProjectSocket {
  state: SocketState;
  reset: () => void;
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
        setState((s) => ({ ...s, connected: true }));
        // The WS itself can't tell us authoritatively whether a run is in
        // progress (init events get replayed; we suppress those). Ask the
        // HTTP API for the canonical `active_run` flag and seed runActive.
        api
          .getProject(projectId)
          .then((p) => {
            setState((s) => ({ ...s, runActive: p.active_run }));
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
        setState((s) => ({ ...s, connected: false }));
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
  };
}
