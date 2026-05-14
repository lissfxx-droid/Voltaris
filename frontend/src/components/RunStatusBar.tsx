import type { AgentProvider } from "../types";

interface Props {
  connected: boolean;
  runActive: boolean;
  provider: AgentProvider | null;
  lastSeq: number;
  lastEvent: string | null;
  lastRunId: number | null;
  lastRunExitCode: number | null;
}

export function RunStatusBar({
  connected,
  runActive,
  provider,
  lastSeq,
  lastEvent,
  lastRunId,
  lastRunExitCode,
}: Props) {
  const runLabel = runActive
    ? "运行中"
    : lastRunId
      ? lastRunExitCode === 0
        ? `Run #${lastRunId} 完成`
        : `Run #${lastRunId} 异常`
      : "待命";

  return (
    <section className="run-status-bar" aria-label="运行状态">
      <div className="run-status-primary" aria-live="polite">
        <span className={`run-pulse${runActive ? " active" : ""}`} aria-hidden="true" />
        <div>
          <div className="run-status-title">{runLabel}</div>
          <div className="run-status-detail">
            {lastEvent || "等待项目事件"}
          </div>
        </div>
      </div>
      <dl className="run-metrics">
        <div>
          <dt>WS</dt>
          <dd className={connected ? "metric-good" : "metric-bad"}>
            {connected ? "已连接" : "未连接"}
          </dd>
        </div>
        <div>
          <dt>Provider</dt>
          <dd>{providerLabel(provider)}</dd>
        </div>
        <div>
          <dt>Seq</dt>
          <dd>{lastSeq || "-"}</dd>
        </div>
      </dl>
    </section>
  );
}

function providerLabel(provider: AgentProvider | null): string {
  if (provider === "codex") return "Codex";
  if (provider === "claude") return "Claude";
  return provider || "-";
}
