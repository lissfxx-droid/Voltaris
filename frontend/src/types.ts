// Shared TypeScript types for backend API + WS messages.

export interface Project {
  id: string;
  name: string;
  created_at: string;
  updated_at: string;
}

export interface FileMeta {
  name: string;
  size: number;
  modified_at: number;
}

export interface ProjectDetail extends Project {
  files: FileMeta[];
  active_run: boolean;
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

// Claude Code stream-json shape (from `claude --output-format stream-json`)
export interface ClaudeSystemInit {
  type: "system";
  subtype?: string;
  [k: string]: unknown;
}

export interface ClaudeAssistantText {
  type: "text";
  text: string;
}

export interface ClaudeAssistantToolUse {
  type: "tool_use";
  id: string;
  name: string;
  input: Record<string, unknown>;
}

export interface ClaudeAssistantThinking {
  type: "thinking";
  thinking: string;
}

export type ClaudeContentBlock =
  | ClaudeAssistantText
  | ClaudeAssistantToolUse
  | ClaudeAssistantThinking
  | { type: string; [k: string]: unknown };

export interface ClaudeAssistant {
  type: "assistant";
  message: {
    content: ClaudeContentBlock[];
    [k: string]: unknown;
  };
  [k: string]: unknown;
}

export interface ClaudeToolResult {
  type: "tool_result";
  tool_use_id: string;
  content: string | Array<{ type: string; text?: string }>;
  is_error?: boolean;
}

export interface ClaudeUser {
  type: "user";
  message: {
    content: (ClaudeToolResult | { type: string; [k: string]: unknown })[];
    [k: string]: unknown;
  };
  [k: string]: unknown;
}

export interface ClaudeResult {
  type: "result";
  [k: string]: unknown;
}

export interface RawLine {
  type: "raw";
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
  | ClaudeSystemInit
  | ClaudeAssistant
  | ClaudeUser
  | ClaudeResult
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
}

export interface ChatToolUseItem {
  kind: "tool_use";
  id: string;
  name: string;
  input: Record<string, unknown>;
  result?: string;
  isError?: boolean;
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
