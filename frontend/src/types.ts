// Shared TypeScript types for backend API + WS messages.

export interface Project {
  id: string;
  name: string;
  created_at: string;
  updated_at: string;
  agent_provider?: AgentProvider | null;
}

export interface FileMeta {
  name: string;
  size: number;
  modified_at: number;
}

export interface ProjectDetail extends Project {
  files: FileMeta[];
  active_run: boolean;
  agent_provider: AgentProvider;
}

export interface RunRecord {
  id: number;
  started_at: string;
  ended_at: string | null;
  user_message: string;
  exit_code: number | null;
}

// --- WebSocket message types ----------------------------------------------------

// Backend control envelopes
export interface WSReady {
  type: "ws_ready";
  since: number;
}

export interface FileUpdated {
  type: "file_updated";
  path: string;
  content: string;
}

export interface FileDeleted {
  type: "file_deleted";
  path: string;
}

export interface RunComplete {
  type: "run_complete";
  run_id: number;
  exit_code: number;
}

export interface SystemError {
  type: "system_error";
  message: string;
}

export interface SystemWarning {
  type: "system_warning";
  message: string;
}

export type AgentProvider = "claude" | "codex" | string;

export interface AgentSession {
  type: "agent_session";
  phase: "started";
  provider: AgentProvider;
  provider_display?: string;
  session_id?: string;
}

export interface AgentMessage {
  type: "agent_message";
  text: string;
  provider?: AgentProvider;
}

export interface AgentTool {
  type: "agent_tool";
  phase: "started" | "finished";
  tool_id: string;
  name?: string;
  input?: Record<string, unknown>;
  result?: string;
  is_error?: boolean;
  provider?: AgentProvider;
}

export interface AgentResult {
  type: "agent_result";
  text: string;
  is_error?: boolean;
  provider?: AgentProvider;
}

export interface AgentSystem {
  type: "agent_system";
  level: "info" | "warning" | "error" | "success";
  message: string;
  provider?: AgentProvider;
}

export interface RawLine {
  type: "agent_raw";
  channel: string;
  text: string;
}

export type WSMessage =
  | WSReady
  | FileUpdated
  | FileDeleted
  | RunComplete
  | SystemError
  | SystemWarning
  | AgentSession
  | AgentMessage
  | AgentTool
  | AgentResult
  | AgentSystem
  | RawLine
  | { type: string; seq?: number; [k: string]: unknown };

// --- Brief frontmatter shape ---------------------------------------------------

export type ProjectStatus = "in_progress" | "awaiting_user" | "completed";

export interface BriefFrontmatter {
  project_id: string;
  project_name: string;
  created_at: string;
  current_phase: number; // 0..7
  status: ProjectStatus;
  phases_completed: number[];
  awaiting_content: string;
  last_modified_files: string[];
  can_generate_final_report: boolean;
}

// --- Render-time chat item (derived from WSMessage) ----------------------------

export interface ChatTextItem {
  kind: "text";
  id: string;
  role: "assistant";
  text: string;
  provider?: AgentProvider;
}

export interface ChatToolUseItem {
  kind: "tool_use";
  id: string;
  name: string;
  input: Record<string, unknown>;
  result?: string;
  isError?: boolean;
  provider?: AgentProvider;
}

export interface ChatSystemItem {
  kind: "system";
  id: string;
  level: "info" | "warning" | "error" | "success";
  text: string;
}

export interface ChatUserItem {
  kind: "user";
  id: string;
  text: string;
}

export type ChatItem =
  | ChatTextItem
  | ChatToolUseItem
  | ChatSystemItem
  | ChatUserItem;
