import { useEffect, useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";

interface Props {
  files: Record<string, string>;
}

const TABS: { key: string; label: string }[] = [
  { key: "00_project_brief.md", label: "状态" },
  { key: "01_requirements.md", label: "1·需求" },
  { key: "02_architecture.md", label: "2·架构" },
  { key: "03_components.md", label: "3·选型" },
  { key: "04_circuit_design.md", label: "4·电路" },
  { key: "05_netlist.md", label: "5·网表" },
  { key: "06_review.md", label: "6·复查" },
  { key: "07_change_log.md", label: "变更" },
  { key: "final_report.md", label: "★报告" },
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

  return (
    <div className="markdown-preview">
      <div className="md-tabs">
        {TABS.map(({ key, label }) => {
          const has = !!files[key]?.trim();
          return (
            <button
              key={key}
              className={`md-tab${active === key ? " active" : ""}${has ? "" : " empty"}`}
              onClick={() => setActive(key)}
              title={key}
            >
              {label}
            </button>
          );
        })}
      </div>

      <div className="md-content">
        {empty ? (
          <div className="muted center">
            {files[active] === undefined
              ? `${active} 还未生成`
              : `${active} 是空的`}
          </div>
        ) : (
          <ReactMarkdown
            remarkPlugins={[remarkGfm, remarkMath]}
            rehypePlugins={[rehypeKatex]}
          >
            {content}
          </ReactMarkdown>
        )}
      </div>
    </div>
  );
}
