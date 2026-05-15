// Thin HTTP client for the FastAPI backend. Vite proxies /api → http://localhost:8000.

import type { AgentProvider, Project, ProjectDetail, RunRecord } from "./types";

const BASE = "/api";

async function http<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      "content-type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText}: ${body}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  health: () => http<{ status: string; agent_provider: AgentProvider }>("/health"),

  listProjects: () => http<Project[]>("/projects"),

  createProject: (name: string) =>
    http<Project>("/projects", {
      method: "POST",
      body: JSON.stringify({ name }),
    }),

  getProject: (id: string) =>
    http<ProjectDetail>(`/projects/${encodeURIComponent(id)}`),

  deleteProject: (id: string) =>
    http<void>(`/projects/${encodeURIComponent(id)}`, { method: "DELETE" }),

  getFile: (id: string, fname: string) =>
    http<{ name: string; content: string }>(
      `/projects/${encodeURIComponent(id)}/files/${encodeURIComponent(fname)}`,
    ),

  listRuns: (id: string) =>
    http<RunRecord[]>(`/projects/${encodeURIComponent(id)}/runs`),

  startRun: (id: string, message: string, agentProvider: AgentProvider) =>
    http<{ run_id: number; project_id: string; status: string; agent_provider: AgentProvider }>(
      `/projects/${encodeURIComponent(id)}/runs`,
      {
        method: "POST",
        body: JSON.stringify({ message, agent_provider: agentProvider }),
      },
    ),

  cancelRun: (id: string) =>
    http<{ run_id: number; status: string }>(
      `/projects/${encodeURIComponent(id)}/runs/cancel`,
      { method: "POST" },
    ),
};
