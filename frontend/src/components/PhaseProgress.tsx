import { useMemo } from "react";

import { PHASES, parseBrief, projectStatusLabel } from "../brief";

interface Props {
  briefContent: string;
  connected: boolean;
  runActive: boolean;
}

export function PhaseProgress({ briefContent, connected, runActive }: Props) {
  const brief = useMemo(() => parseBrief(briefContent), [briefContent]);
  const status = projectStatusLabel(brief, connected, runActive);

  return (
    <div className="phase-progress">
      <div className="phase-header">
        <div className="phase-title">
          {brief?.project_name || "未初始化"}
          <span className="phase-status">● {status}</span>
        </div>
        {brief?.awaiting_content && brief.status === "awaiting_user" && (
          <div className="phase-awaiting">{brief.awaiting_content}</div>
        )}
      </div>

      <div className="phase-bar">
        {PHASES.map(({ num, label }) => {
          const completed = brief?.phases_completed?.includes(num);
          const current = brief?.current_phase === num;
          const awaiting = current && brief?.status === "awaiting_user";
          let cls = "phase-segment";
          if (completed) cls += " phase-done";
          else if (current && runActive) cls += " phase-active";
          else if (awaiting) cls += " phase-waiting";
          return (
            <div key={num} className={cls} title={`Phase ${num}: ${label}`}>
              <span className="phase-num">{num}</span>
              <span className="phase-label">{label}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
