import { useEffect, useMemo, useState } from "react";

import { compactId, parseBrief, projectStatusLabel } from "./brief";
import { ChatPanel } from "./components/ChatPanel";
import { MarkdownPreview } from "./components/MarkdownPreview";
import { PhaseProgress } from "./components/PhaseProgress";
import { ProjectList } from "./components/ProjectList";
import { ResizeHandle } from "./components/ResizeHandle";
import { useProjectSocket } from "./ws";

const LS_LEFT = "pcb.col.left";
const LS_RIGHT = "pcb.col.right";

function loadWidth(key: string, fallback: number): number {
  const raw = localStorage.getItem(key);
  if (!raw) return fallback;
  const n = Number(raw);
  return Number.isFinite(n) && n > 0 ? n : fallback;
}

export function App() {
  const [activeId, setActiveId] = useState<string | null>(null);
  const { state } = useProjectSocket(activeId);
  const briefContent = state.files["00_project_brief.md"] ?? "";
  const brief = useMemo(() => parseBrief(briefContent), [briefContent]);

  const [leftW, setLeftW] = useState<number>(() => loadWidth(LS_LEFT, 280));
  const [rightW, setRightW] = useState<number>(() => loadWidth(LS_RIGHT, 520));

  useEffect(() => {
    localStorage.setItem(LS_LEFT, String(leftW));
  }, [leftW]);
  useEffect(() => {
    localStorage.setItem(LS_RIGHT, String(rightW));
  }, [rightW]);

  const gridTemplate = `${leftW}px 6px 1fr 6px ${rightW}px`;
  const statusLabel = projectStatusLabel(brief, state.connected, state.runActive);
  const currentPhase = brief?.current_phase
    ? `${brief.current_phase}/7`
    : state.files["00_project_brief.md"]
      ? "0/7"
      : "未初始化";
  const fileCount = Object.keys(state.files).length;

  return (
    <div className="app-shell">
      <header className="workspace-header">
        <div className="brand-block">
          <div className="brand-mark" aria-hidden="true">
            V
          </div>
          <div>
            <div className="brand-title">Voltaris</div>
            <div className="brand-subtitle">AI PCB design workbench</div>
          </div>
        </div>
        <div className="workspace-context" aria-live="polite">
          <div>
            <span className="context-label">项目</span>
            <strong>{brief?.project_name || compactId(activeId)}</strong>
          </div>
          <div>
            <span className="context-label">阶段</span>
            <strong>{currentPhase}</strong>
          </div>
          <div>
            <span className="context-label">产物</span>
            <strong>{fileCount}</strong>
          </div>
          <div className={`status-chip status-${statusLabel}`}>
            <span className="status-dot" aria-hidden="true" />
            {statusLabel}
          </div>
        </div>
      </header>

      <div className="app" style={{ gridTemplateColumns: gridTemplate }}>
        <aside className="col-left" aria-label="项目导航">
          <ProjectList activeId={activeId} onSelect={setActiveId} />
        </aside>

        <ResizeHandle side="left" width={leftW} setWidth={setLeftW} min={220} max={520} />

        <main className="col-mid" aria-label="运行对话">
          {activeId ? (
            <>
              <PhaseProgress
                briefContent={briefContent}
                connected={state.connected}
                runActive={state.runActive}
              />
              <ChatPanel
                projectId={activeId}
                chat={state.chat}
                runActive={state.runActive}
                connected={state.connected}
              />
            </>
          ) : (
            <div className="empty-state">
              <div className="empty-kicker">工程工作台</div>
              <h1>选择项目后开始设计流</h1>
              <p>左侧创建或打开项目，Voltaris 会在这里显示 run 对话、阶段进度和实时产物。</p>
            </div>
          )}
        </main>

        <ResizeHandle side="right" width={rightW} setWidth={setRightW} min={360} max={1200} />

        <aside className="col-right" aria-label="设计产物预览">
          {activeId ? (
            <MarkdownPreview files={state.files} />
          ) : (
            <div className="artifact-empty">
              <span className="artifact-empty-label">Artifacts</span>
              <p>阶段文档、网表和最终报告会在项目运行后显示。</p>
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}
