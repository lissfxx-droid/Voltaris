import { useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";

import { api } from "../api";

interface Props {
  projectId: string;
  files: Record<string, string>;
  runActive: boolean;
  onSaved: (path: string, content: string) => void;
}

type ViewMode = "preview" | "source";

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

const EDITABLE_EXTENSIONS = [".md", ".yaml", ".yml"];

// Strip the YAML frontmatter so the rendered preview shows only the prose.
function stripFrontmatter(content: string): string {
  return content.replace(/^---\n[\s\S]*?\n---\n*/, "");
}

export function MarkdownPreview({ projectId, files, runActive, onSaved }: Props) {
  // Pick a sensible default tab: the most recently populated file.
  const initialTab = useMemo(() => {
    for (let i = TABS.length - 1; i >= 0; i--) {
      const k = TABS[i].key;
      if (files[k]?.trim()) return k;
    }
    return TABS[0].key;
  }, [Object.keys(files).join("|")]);

  const [active, setActive] = useState<string>(initialTab);
  const [mode, setMode] = useState<ViewMode>("preview");
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(files[initialTab] ?? "");
  const [baseContent, setBaseContent] = useState(files[initialTab] ?? "");
  const [saveError, setSaveError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [pendingExternal, setPendingExternal] = useState(false);
  const [lastActive, setLastActive] = useState(active);
  // Once the user explicitly picks a tab we stop auto-following `initialTab`.
  // Without this, clicking an empty/PENDING tab triggered the auto-revert
  // effect on the very next render and snapped the view back to the brief,
  // producing a visible flicker (bug PCB-25 #2).
  const userPickedRef = useRef(false);

  const pickTab = (key: string) => {
    userPickedRef.current = true;
    setActive(key);
  };

  // Reset the user-pick tracker when switching projects so the new project
  // can still auto-follow its own latest populated file.
  useEffect(() => {
    userPickedRef.current = false;
    setActive(initialTab);
  }, [projectId]);

  // Auto-follow `initialTab` only when the user has not made an explicit
  // selection yet (e.g. files arrive after first mount and there is now a
  // sensible default to pick).
  useEffect(() => {
    if (!userPickedRef.current && initialTab !== active && !editing) {
      setActive(initialTab);
    }
  }, [active, editing, initialTab]);

  const raw = files[active] ?? "";
  const displayedRaw = editing ? draft : raw;
  const content = stripFrontmatter(displayedRaw);
  const empty = !content.trim();
  const activeTab = TABS.find((tab) => tab.key === active) ?? TABS[0];
  const lineCount = displayedRaw ? displayedRaw.split("\n").length : 0;
  const charCount = displayedRaw.length;
  const isCodeArtifact = active.endsWith(".yaml") || active.endsWith(".yml");
  const isEditable = EDITABLE_EXTENSIONS.some((ext) => active.endsWith(ext));
  const dirty = draft !== baseContent;
  const editLocked = runActive;
  const canEdit = isEditable && !editLocked && !saving;
  const showSource = editing || mode === "source" || isCodeArtifact;

  useEffect(() => {
    const latest = files[active] ?? "";
    if (active !== lastActive) {
      setLastActive(active);
      setDraft(latest);
      setBaseContent(latest);
      setSaveError(null);
      setNotice(null);
      setPendingExternal(false);
      setEditing(false);
      setMode(isCodeArtifact ? "source" : "preview");
      return;
    }

    if (editing) {
      if (latest !== baseContent && latest !== draft) {
        setPendingExternal(true);
      }
      return;
    }
    setDraft(latest);
    setBaseContent(latest);
    setPendingExternal(false);
  }, [active, baseContent, draft, editing, files, isCodeArtifact, lastActive]);

  useEffect(() => {
    if (runActive && editing) {
      setEditing(false);
      setDraft(raw);
      setBaseContent(raw);
      setSaveError(null);
      setPendingExternal(false);
      setNotice("Run 已开始，编辑已关闭，产物会继续实时刷新。");
    }
  }, [editing, raw, runActive]);

  const startEditing = () => {
    if (!canEdit) return;
    const latest = files[active] ?? "";
    setDraft(latest);
    setBaseContent(latest);
    setEditing(true);
    setMode("source");
    setSaveError(null);
    setNotice(null);
    setPendingExternal(false);
  };

  const cancelEditing = () => {
    setDraft(files[active] ?? "");
    setBaseContent(files[active] ?? "");
    setEditing(false);
    setSaveError(null);
    setPendingExternal(false);
  };

  const useLatestExternal = () => {
    const latest = files[active] ?? "";
    setDraft(latest);
    setBaseContent(latest);
    setPendingExternal(false);
    setSaveError(null);
  };

  const saveDraft = async () => {
    if (!dirty || saving || runActive) return;
    setSaving(true);
    setSaveError(null);
    setNotice(null);
    try {
      const saved = await api.saveFile(projectId, active, draft);
      onSaved(saved.name, saved.content);
      setBaseContent(saved.content);
      setDraft(saved.content);
      setEditing(false);
      setPendingExternal(false);
      setNotice("已保存到项目 workdir。");
    } catch (error) {
      setSaveError(formatSaveError(error));
    } finally {
      setSaving(false);
    }
  };

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
              onClick={() => pickTab(key)}
              title={has ? `${key} · 可查看` : `${key} · 暂无内容`}
              disabled={editing && dirty}
            >
              <span className="md-tab-label">{label}</span>
              {has && (
                <span
                  className="md-tab-state-icon"
                  aria-label="可查看"
                  title="可查看"
                >
                  {/* 单一"眼睛"图标，替代之前每个 tab 重复的 READY / PENDING
                      文本列（PCB-25 #3 走查反馈）。 */}
                  <EyeIcon />
                </span>
              )}
            </button>
          );
        })}
      </div>

      <div className="artifact-toolbar" aria-label="产物操作">
        <div className="view-switch" role="group" aria-label="查看模式">
          <button
            type="button"
            className={mode === "preview" && !editing ? "active" : ""}
            onClick={() => setMode("preview")}
            disabled={editing || isCodeArtifact}
          >
            预览
          </button>
          <button
            type="button"
            className={mode === "source" || editing ? "active" : ""}
            onClick={() => setMode("source")}
          >
            源码
          </button>
        </div>

        <div className="edit-actions">
          {editing ? (
            <>
              <button type="button" onClick={cancelEditing} disabled={saving}>
                取消
              </button>
              <button
                type="button"
                className="btn-primary"
                onClick={saveDraft}
                disabled={!dirty || saving || runActive}
              >
                {saving ? "保存中..." : "保存"}
              </button>
            </>
          ) : (
            <button type="button" onClick={startEditing} disabled={!canEdit}>
              编辑
            </button>
          )}
        </div>
      </div>

      {(pendingExternal || saveError || notice) && (
        <div
          className={`artifact-notice${
            saveError ? " error" : pendingExternal ? " warning" : ""
          }`}
          role={saveError || pendingExternal ? "alert" : "status"}
        >
          <span>
            {saveError ||
              (pendingExternal
                ? "文件在编辑期间收到实时更新，保存会覆盖当前远端内容。"
                : notice)}
          </span>
          {pendingExternal && (
            <button type="button" onClick={useLatestExternal} disabled={saving}>
              使用最新内容
            </button>
          )}
        </div>
      )}

      <div className={`md-content${isCodeArtifact ? " md-code-artifact" : ""}${showSource ? " source-mode" : ""}`}>
        {empty && !editing ? null : showSource ? (
          editing ? (
            <textarea
              className="md-editor"
              aria-label={`${activeTab.label} Markdown 源码`}
              value={draft}
              onChange={(e) => {
                setDraft(e.target.value);
                setSaveError(null);
                setNotice(null);
              }}
              spellCheck={false}
              disabled={saving || runActive}
            />
          ) : (
            <pre className="artifact-code"><code>{displayedRaw}</code></pre>
          )
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

function formatBytes(chars: number): string {
  if (!chars) return "0 B";
  if (chars < 1024) return `${chars} B`;
  return `${(chars / 1024).toFixed(1)} KB`;
}

function formatSaveError(error: unknown): string {
  const text = String(error);
  if (text.includes("409")) return "当前项目正在运行，保存被锁定。";
  return `保存失败: ${text}`;
}

function EyeIcon() {
  return (
    <svg
      width="12"
      height="12"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M1.5 8s2.5-4.5 6.5-4.5S14.5 8 14.5 8 12 12.5 8 12.5 1.5 8 1.5 8z" />
      <circle cx="8" cy="8" r="2.2" />
    </svg>
  );
}
