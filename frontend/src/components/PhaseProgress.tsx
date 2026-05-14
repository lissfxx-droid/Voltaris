// Parses the YAML frontmatter at the top of 00_project_brief.md and
// renders a 7-segment phase bar.

import { useMemo } from "react";
import yaml from "js-yaml";

import type { BriefFrontmatter } from "../types";

interface Props {
  briefContent: string;
  connected: boolean;
  runActive: boolean;
}

const PHASES = [
  { num: 1, label: "需求", file: "01_requirements.md" },
  { num: 2, label: "架构", file: "02_architecture.md" },
  { num: 3, label: "选型", file: "03_components.md" },
  { num: 4, label: "电路", file: "04_circuit_design.md" },
  { num: 5, label: "网表", file: "05_netlist.md" },
  { num: 6, label: "复查", file: "06_review.md" },
  { num: 7, label: "报告", file: "final_report.md" },
];

function parseBrief(content: string): BriefFrontmatter | null {
  if (!content) return null;
  const match = content.match(/^---\n([\s\S]*?)\n---/);
  if (!match) return null;
  try {
    const fm = yaml.load(match[1]) as Partial<BriefFrontmatter> | null;
    if (!fm || typeof fm !== "object") return null;
    return {
      project_id: String(fm.project_id ?? ""),
      project_name: String(fm.project_name ?? ""),
      created_at: String(fm.created_at ?? ""),
      current_phase: Number(fm.current_phase ?? 0),
      status:
        fm.status === "completed" || fm.status === "awaiting_user"
          ? fm.status
          : "in_progress",
      phases_completed: Array.isArray(fm.phases_completed)
        ? fm.phases_completed.map(Number)
        : [],
      awaiting_content: String(fm.awaiting_content ?? ""),
      last_modified_files: Array.isArray(fm.last_modified_files)
        ? fm.last_modified_files.map(String)
        : [],
      can_generate_final_report: !!fm.can_generate_final_report,
    };
  } catch {
    return null;
  }
}

export function PhaseProgress({ briefContent, connected, runActive }: Props) {
  const brief = useMemo(() => parseBrief(briefContent), [briefContent]);

  return (
    <div className="phase-progress">
      <div className="phase-header">
        <div className="phase-title">
          {brief?.project_name || "未初始化"}
          <span className="phase-status">
            {!connected
              ? "● 未连接"
              : runActive
                ? "● 运行中"
                : brief?.status === "completed"
                  ? "● 已完成"
                  : brief?.status === "awaiting_user"
                    ? "● 等待确认"
                    : "● 就绪"}
          </span>
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
