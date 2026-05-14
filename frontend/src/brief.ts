import yaml from "js-yaml";

import type { BriefFrontmatter } from "./types";

export const PHASES = [
  { num: 1, label: "需求", file: "01_requirements.md" },
  { num: 2, label: "架构", file: "02_architecture.md" },
  { num: 3, label: "选型", file: "03_components.md" },
  { num: 4, label: "电路", file: "04_circuit_design.md" },
  { num: 5, label: "网表", file: "05_netlist.md" },
  { num: 6, label: "复查", file: "06_review.md" },
  { num: 7, label: "报告", file: "final_report.md" },
] as const;

export function parseBrief(content: string): BriefFrontmatter | null {
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

export function projectStatusLabel(
  brief: BriefFrontmatter | null,
  connected: boolean,
  runActive: boolean,
): string {
  if (!connected) return "未连接";
  if (runActive) return "运行中";
  if (brief?.status === "completed") return "已完成";
  if (brief?.status === "awaiting_user") return "等待确认";
  return "就绪";
}

export function compactId(id: string | null): string {
  return id ? id.slice(0, 8) : "未选择";
}
