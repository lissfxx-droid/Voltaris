import { useMutation } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { api } from "../api";
import type { AgentProvider, ChatItem, ChatToolUseItem } from "../types";

interface Props {
  projectId: string;
  chat: ChatItem[];
  runActive: boolean;
  connected: boolean;
}

export function ChatPanel({ projectId, chat, runActive, connected }: Props) {
  const [input, setInput] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

  const startMut = useMutation({
    mutationFn: (message: string) => api.startRun(projectId, message),
    onSuccess: () => setInput(""),
  });

  const cancelMut = useMutation({
    mutationFn: () => api.cancelRun(projectId),
  });

  // A 404 from cancel means the run already ended (race between server cleanup
  // and the run_complete event reaching the client). Treat as success.
  const cancelError =
    cancelMut.isError && !String(cancelMut.error).includes("404")
      ? cancelMut.error
      : null;

  // Auto-scroll to bottom on new messages.
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [chat.length, runActive]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const text = input.trim();
    if (!text || runActive) return;
    startMut.mutate(text);
  };

  const canSend = !runActive && !startMut.isPending && connected;

  return (
    <div className="chat-panel">
      <div className="chat-messages" ref={scrollRef}>
        {chat.length === 0 && (
          <div className="muted center">
            还没有对话。在下方输入需求开始（例如：做一个 ESP32 温控器，4 路温度采集，蓝牙配网）
          </div>
        )}
        {chat.map((it) => (
          <ChatBubble key={it.id} item={it} />
        ))}
        {runActive && <RunIndicator />}
      </div>

      <form className="chat-input" onSubmit={handleSubmit}>
        <textarea
          placeholder={
            runActive
              ? "AI 正在运行..."
              : "输入消息（Cmd/Ctrl+Enter 发送）"
          }
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
              handleSubmit(e);
            }
          }}
          disabled={!canSend}
          rows={3}
        />
        <div className="chat-input-actions">
          <span className="hint">
            {!connected
              ? "WS 未连接"
              : runActive
                ? "运行中..."
                : "Cmd/Ctrl+Enter 发送"}
          </span>
          {runActive ? (
            <button
              type="button"
              className="btn-stop"
              onClick={() => cancelMut.mutate()}
              disabled={cancelMut.isPending}
            >
              ■ 停止
            </button>
          ) : (
            <button type="submit" disabled={!canSend || !input.trim()}>
              发送
            </button>
          )}
        </div>
        {startMut.isError && (
          <div className="error">启动 run 失败: {String(startMut.error)}</div>
        )}
        {cancelMut.isError && cancelError && (
          <div className="error">中断失败: {String(cancelError)}</div>
        )}
      </form>
    </div>
  );
}

function ChatBubble({ item }: { item: ChatItem }) {
  if (item.kind === "text") {
    return (
      <div className="bubble bubble-assistant">
        <div className="bubble-role">{providerLabel(item.provider)}</div>
        <div className="bubble-text bubble-md">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{item.text}</ReactMarkdown>
        </div>
      </div>
    );
  }
  if (item.kind === "user") {
    return (
      <div className="bubble bubble-user">
        <div className="bubble-role">你</div>
        <div className="bubble-text">{item.text}</div>
      </div>
    );
  }
  if (item.kind === "system") {
    // success/error usually carry the provider's formatted final summary — render
    // markdown so headings, lists and code spans show. info/warning are
    // short status strings; keep them as plain text.
    const isMd = item.level === "success" || item.level === "error";
    return (
      <div className={`system-line system-${item.level}${isMd ? " system-md" : ""}`}>
        {isMd ? (
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{item.text}</ReactMarkdown>
        ) : (
          item.text
        )}
      </div>
    );
  }
  return <ToolUseCard item={item} />;
}

function providerLabel(provider?: AgentProvider): string {
  if (provider === "codex") return "Codex";
  if (provider === "claude") return "Claude";
  return "AI";
}

function ToolUseCard({ item }: { item: ChatToolUseItem }) {
  const [open, setOpen] = useState(false);
  const isAgent = item.name === "Task" || item.name === "Agent";
  const subagent =
    isAgent && typeof item.input.subagent_type === "string"
      ? (item.input.subagent_type as string)
      : null;
  const desc =
    typeof item.input.description === "string"
      ? (item.input.description as string)
      : null;
  const summary = subagent
    ? `Agent → ${subagent}${desc ? ` · ${desc}` : ""}`
    : `${item.name}${desc ? ` · ${desc}` : ""}`;

  return (
    <div className={`tool-card${item.isError ? " tool-error" : ""}${isAgent ? " tool-agent" : ""}`}>
      <button className="tool-summary" onClick={() => setOpen(!open)}>
        <span className="tool-icon">{open ? "▾" : "▸"}</span>
        <span className="tool-name">{summary}</span>
        <span className="tool-status">
          {item.result === undefined ? "运行中..." : item.isError ? "错误" : "完成"}
        </span>
      </button>
      {open && (
        <div className="tool-detail">
          <div className="tool-section">
            <div className="tool-section-title">Input</div>
            <pre>{JSON.stringify(item.input, null, 2)}</pre>
          </div>
          {item.result !== undefined && (
            <div className="tool-section">
              <div className="tool-section-title">Result</div>
              <pre>{item.result}</pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function RunIndicator() {
  return (
    <div className="run-indicator">
      <span className="dot" />
      <span className="dot" />
      <span className="dot" />
    </div>
  );
}
