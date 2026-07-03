export interface ChatRequest {
  question: string;
  user_id: string;
  conversation_id: number | null;
}

export interface Citation {
  source: string;
  content: string;
  section: string;
  section_title: string;
  chunk_index: number;
  download_url?: string;
}

export interface Conversation {
  id: number;
  user_id: string;
  title: string | null;
  created_at: string;
}

export interface Message {
  id: number;
  conversation_id: number;
  role: "user" | "assistant";
  content: string;
  route: string | null;
  citations: Citation[];
  created_at: string;
}

export interface HealthResponse {
  status: string;
  ollama_reachable: boolean;
  telegram_configured: boolean;
  otel_enabled: boolean;
  otel_ui_url: string;
}

export interface IngestResponse {
  doc_id: string;
  source: string;
  page_count: number;
  chunks_indexed: number;
  duration_s: number;
  markdown_path: string;
  metadata_path: string;
}

export interface PlanStatus {
  plan_id: string;
  state: "suspended" | "approved" | "rejected" | "done";
  pending_step_id: string | null;
  trigger_case: string | null;
  expires_at: string | null;
  conversation_id: number | null;
}

// NDJSON streaming event discriminated union
export interface ConversationEvent {
  type: "conversation";
  conversation_id: number;
}

export interface StageEvent {
  type: "stage";
  node: string;
  status: "started" | "done";
  info?: string;
}

export interface TokenEvent {
  type: "token";
  value: string;
}

export interface MetaEvent {
  type: "meta";
  reformulated_query: string;
}

export interface ApprovalRequiredEvent {
  type: "approval_required";
  plan_id: string;
  step_id: string;
  message: string;
  expires_at: string;
  trigger_case: string;
}

export interface DoneEvent {
  type: "done";
  citations: Citation[];
  validated: boolean;
  retry_count: number;
  critique: string;
  route: string;
  target_year: number | null;
  plan_id: string | null;
  data_operation: unknown | null;
  report_kind: string | null;
  report_year: number | null;
  report_run_id: string | null;
}

export interface ErrorEvent {
  type: "error";
  value: string;
}

export type NDJSONEvent =
  | ConversationEvent
  | StageEvent
  | TokenEvent
  | MetaEvent
  | ApprovalRequiredEvent
  | DoneEvent
  | ErrorEvent;
