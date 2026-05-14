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
        <h2>项目</h2>
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
              <div className="name">{p.name}</div>
              <div className="id">{p.id}</div>
            </button>
            <button
              className="btn-icon"
              title="删除"
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
