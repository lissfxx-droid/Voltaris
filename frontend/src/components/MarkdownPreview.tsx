import { useEffect, useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";

interface Props {
  files: Record<string, string>;
}

const TABS: { key: string; label: string; short: string; group: string }[] = [
  { key: "00_project_brief.md", label: "项目状态", short: "状态", group: "State" },
  { key: "01_requirements.md", label: "需求分析", short: "1", group: "Phase" },
  { key: "02_architecture.md", label: "系统架构", short: "2", group: "Phase" },
  { key: "03_components.md", label: "器件选型", short: "3", group: "Phase" },
  { key: "04_circuit_design.md", label: "电路设计", short: "4", group: "Phase" },
  { key: "05_netlist.md", label: "网表说明", short: "5", group: "Phase" },
  { key: "06_review.md", label: "设计复查", short: "6", group: "Phase" },
  { key: "07_change_log.md", label: "变更记录", short: "变更", group: "Log" },
  { key: "final_report.md", label: "最终报告", short: "报告", group: "Report" },
  { key: "05_circuit.thinir.yaml", label: "CircuitIR YAML", short: "YAML", group: "IR" },
];

// Strip the YAML frontmatter so the rendered preview shows only the prose.
function stripFrontmatter(content: string): string {
  return content.replace(/^---\n[\s\S]*?\n---\n*/, "");
}

export function MarkdownPreview({ files }: Props) {
  // Pick a sensible default tab: the most recently populated file.
  const initialTab = useMemo(() => {
    for (let i = TABS.length - 1; i >= 0; i--) {
      const k = TABS[i].key;
      if (files[k]?.trim()) return k;
    }
    return TABS[0].key;
  }, [Object.keys(files).join("|")]);

  const [active, setActive] = useState<string>(initialTab);

  // If the chosen tab becomes available later (e.g. file written mid-run),
  // keep the user's manual selection unless they're still on the default.
  useEffect(() => {
    if (!files[active]?.trim() && initialTab !== active) {
      setActive(initialTab);
    }
  }, [initialTab]);

  const raw = files[active] ?? "";
  const content = stripFrontmatter(raw);
  const empty = !content.trim();
  const activeTab = TABS.find((tab) => tab.key === active) ?? TABS[0];
  const lineCount = raw ? raw.split("\n").length : 0;
  const charCount = raw.length;
  const isCodeArtifact = active.endsWith(".yaml") || active.endsWith(".yml");

  return (
    <div className="markdown-preview">
      <div className="artifact-header">
        <div>
          <div className="artifact-kicker">{activeTab.group}</div>
          <h2>{activeTab.label}</h2>
        </div>
        <div className="artifact-meta" aria-label="产物元信息">
          <span>{active}</span>
          <span>{lineCount || 0} lines</span>
          <span>{formatBytes(charCount)}</span>
        </div>
      </div>

      <div className="md-tabs" role="tablist" aria-label="设计产物">
        {TABS.map(({ key, label }) => {
          const has = !!files[key]?.trim();
          return (
            <button
              key={key}
              type="button"
              role="tab"
              aria-selected={active === key}
              className={`md-tab${active === key ? " active" : ""}${has ? "" : " empty"}`}
              onClick={() => setActive(key)}
              title={key}
            >
              <span className="md-tab-label">{label}</span>
              <span className="md-tab-state">{has ? "ready" : "pending"}</span>
            </button>
          );
        })}
      </div>

      <div className={`md-content${isCodeArtifact ? " md-code-artifact" : ""}`}>
        {empty ? (
          <div className="muted center">
            {files[active] === undefined
              ? `${active} 还未生成`
              : `${active} 是空的`}
          </div>
        ) : (
          isCodeArtifact ? (
            <pre className="artifact-code"><code>{raw}</code></pre>
          ) : (
            <ReactMarkdown
              remarkPlugins={[remarkGfm, remarkMath]}
              rehypePlugins={[rehypeKatex]}
            >
              {content}
            </ReactMarkdown>
          )
        )}
      </div>
    </div>
  );
}

function formatBytes(chars: number): string {
  if (!chars) return "0 B";
  if (chars < 1024) return `${chars} B`;
  return `${(chars / 1024).toFixed(1)} KB`;
}
