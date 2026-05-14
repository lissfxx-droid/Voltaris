import { useEffect, useState } from "react";

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

  const [leftW, setLeftW] = useState<number>(() => loadWidth(LS_LEFT, 240));
  const [rightW, setRightW] = useState<number>(() => loadWidth(LS_RIGHT, 480));

  useEffect(() => {
    localStorage.setItem(LS_LEFT, String(leftW));
  }, [leftW]);
  useEffect(() => {
    localStorage.setItem(LS_RIGHT, String(rightW));
  }, [rightW]);

  const gridTemplate = `${leftW}px 6px 1fr 6px ${rightW}px`;

  return (
    <div className="app" style={{ gridTemplateColumns: gridTemplate }}>
      <aside className="col-left">
        <ProjectList activeId={activeId} onSelect={setActiveId} />
      </aside>

      <ResizeHandle side="left" width={leftW} setWidth={setLeftW} min={180} max={520} />

      <main className="col-mid">
        {activeId ? (
          <>
            <PhaseProgress
              briefContent={state.files["00_project_brief.md"] ?? ""}
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
            <h2>选择一个项目，或新建一个开始设计</h2>
            <p>左侧栏点击 + 新建项目</p>
          </div>
        )}
      </main>

      <ResizeHandle side="right" width={rightW} setWidth={setRightW} min={280} max={1200} />

      <aside className="col-right">
        {activeId && <MarkdownPreview files={state.files} />}
      </aside>
    </div>
  );
}
