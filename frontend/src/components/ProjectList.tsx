import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "../api";
import type { AgentProvider, Project } from "../types";

interface Props {
  activeId: string | null;
  onSelect: (id: string | null) => void;
}

type RuntimeChoice = "claude" | "codex";

const RUNTIME_OPTIONS: Array<{ value: RuntimeChoice; label: string; hint: string }> = [
  { value: "claude", label: "Claude", hint: "Claude Code 编排器，支持原生 Agent 工具协议" },
  { value: "codex", label: "Codex", hint: "Codex CLI，按内联子代理方式执行" },
];

function providerDisplay(provider?: AgentProvider | null): string {
  if (provider === "codex") return "Codex";
  if (provider === "claude") return "Claude";
  return "Claude";
}

export function ProjectList({ activeId, onSelect }: Props) {
  const qc = useQueryClient();
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [runtime, setRuntime] = useState<RuntimeChoice>("claude");

  const { data: projects = [], isLoading } = useQuery({
    queryKey: ["projects"],
    queryFn: api.listProjects,
    refetchInterval: 10_000,
  });

  const createMut = useMutation({
    mutationFn: (input: { name: string; runtime: RuntimeChoice }) =>
      api.createProject(input.name, input.runtime),
    onSuccess: (proj: Project) => {
      qc.invalidateQueries({ queryKey: ["projects"] });
      onSelect(proj.id);
      setCreating(false);
      setNewName("");
      setRuntime("claude");
    },
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => api.deleteProject(id),
    onSuccess: (_void, id) => {
      qc.invalidateQueries({ queryKey: ["projects"] });
      if (activeId === id) onSelect(null);
    },
  });

  const handleCreate = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = newName.trim();
    if (trimmed) createMut.mutate({ name: trimmed, runtime });
  };

  return (
    <div className="project-list">
      <div className="project-list-header">
        <div>
          <h2>项目</h2>
          <p>{projects.length ? `${projects.length} 个工作区` : "等待创建"}</p>
        </div>
        <button
          className="btn-primary"
          onClick={() => setCreating(true)}
          disabled={creating}
        >
          + 新建
        </button>
      </div>

      {creating && (
        <form className="project-create-form" onSubmit={handleCreate}>
          <input
            autoFocus
            id="project-name"
            name="projectName"
            autoComplete="off"
            aria-label="项目名"
            placeholder="项目名 (建议 ASCII)"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            disabled={createMut.isPending}
          />
          <div
            className={`runtime-selector runtime-selector-create${createMut.isPending ? " is-disabled" : ""}`}
            role="radiogroup"
            aria-label="选择 AI 运行时"
          >
            <div className="runtime-options">
              {RUNTIME_OPTIONS.map((option) => {
                const checked = runtime === option.value;
                return (
                  <label
                    key={option.value}
                    className={`runtime-option${checked ? " selected" : ""}`}
                    title={option.hint}
                  >
                    <input
                      type="radio"
                      name="agent-provider"
                      value={option.value}
                      checked={checked}
                      onChange={() => setRuntime(option.value)}
                      disabled={createMut.isPending}
                    />
                    <span>{option.label}</span>
                  </label>
                );
              })}
            </div>
          </div>
          <div className="form-actions">
            <button type="submit" disabled={!newName.trim() || createMut.isPending}>
              创建
            </button>
            <button
              type="button"
              onClick={() => {
                setCreating(false);
                setNewName("");
                setRuntime("claude");
              }}
              disabled={createMut.isPending}
            >
              取消
            </button>
          </div>
          {createMut.isError && (
            <div className="error">{String(createMut.error)}</div>
          )}
        </form>
      )}

      <ul className="project-items">
        {isLoading && <li className="muted">加载中...</li>}
        {!isLoading && projects.length === 0 && (
          <li className="muted">还没有项目</li>
        )}
        {projects.map((p) => (
          <li
            key={p.id}
            className={`project-item${activeId === p.id ? " active" : ""}`}
          >
            <button className="project-item-name" onClick={() => onSelect(p.id)}>
              <span className="name-row">
                <span className="name">{p.name}</span>
                {activeId === p.id && <span className="active-pill">当前</span>}
              </span>
              <span className="project-meta">
                <span>{shortId(p.id)}</span>
                <span className="project-runtime">{providerDisplay(p.agent_provider)}</span>
                <span>{formatDate(p.updated_at)}</span>
              </span>
            </button>
            <button
              className="btn-icon"
              title="删除"
              aria-label={`删除项目 ${p.name}`}
              onClick={() => {
                if (confirm(`确定删除「${p.name}」？workdir 也会删除`)) {
                  deleteMut.mutate(p.id);
                }
              }}
            >
              ×
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

function shortId(id: string): string {
  return id.slice(0, 8);
}

function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "时间未知";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}
