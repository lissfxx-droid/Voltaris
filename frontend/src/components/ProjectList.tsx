import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "../api";
import type { Project } from "../types";

interface Props {
  activeId: string | null;
  onSelect: (id: string | null) => void;
}

export function ProjectList({ activeId, onSelect }: Props) {
  const qc = useQueryClient();
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");

  const { data: projects = [], isLoading } = useQuery({
    queryKey: ["projects"],
    queryFn: api.listProjects,
    refetchInterval: 10_000,
  });

  const createMut = useMutation({
    mutationFn: (name: string) => api.createProject(name),
    onSuccess: (proj: Project) => {
      qc.invalidateQueries({ queryKey: ["projects"] });
      onSelect(proj.id);
      setCreating(false);
      setNewName("");
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
    if (trimmed) createMut.mutate(trimmed);
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
          <div className="form-actions">
            <button type="submit" disabled={!newName.trim() || createMut.isPending}>
              创建
            </button>
            <button
              type="button"
              onClick={() => {
                setCreating(false);
                setNewName("");
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
