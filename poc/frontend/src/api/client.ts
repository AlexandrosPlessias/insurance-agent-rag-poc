import type {
  ChatRequest,
  Conversation,
  HealthResponse,
  IngestResponse,
  Message,
  NDJSONEvent,
  PlanStatus,
} from "./types";

const BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://localhost:8000";

async function* parseNDJSON(response: Response): AsyncGenerator<NDJSONEvent> {
  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop()!;
    for (const line of lines) {
      if (line.trim()) yield JSON.parse(line) as NDJSONEvent;
    }
  }
  if (buffer.trim()) yield JSON.parse(buffer) as NDJSONEvent;
}

export async function getHealth(): Promise<HealthResponse> {
  const r = await fetch(`${BASE}/health`);
  return r.json() as Promise<HealthResponse>;
}

export async function* streamChat(req: ChatRequest): AsyncGenerator<NDJSONEvent> {
  const r = await fetch(`${BASE}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  yield* parseNDJSON(r);
}

export async function* streamPlanResume(planId: string): AsyncGenerator<NDJSONEvent> {
  const r = await fetch(`${BASE}/plans/${encodeURIComponent(planId)}/resume/stream`);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  yield* parseNDJSON(r);
}

export async function listConversations(userId: string): Promise<Conversation[]> {
  const r = await fetch(`${BASE}/conversations?user_id=${encodeURIComponent(userId)}`);
  return r.json();
}

export async function createConversation(
  userId: string,
  title?: string
): Promise<Conversation> {
  const r = await fetch(`${BASE}/conversations`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: userId, title: title ?? null }),
  });
  return r.json();
}

export async function getMessages(convId: number): Promise<Message[]> {
  const r = await fetch(`${BASE}/conversations/${convId}/messages`);
  return r.json();
}

export async function deleteConversation(convId: number): Promise<void> {
  await fetch(`${BASE}/conversations/${convId}`, { method: "DELETE" });
}

export async function submitFeedback(
  traceId: string,
  score: -1 | 0 | 1,
  userId: string,
  planId: string,
  conversationId: number | null,
  comment?: string
): Promise<void> {
  const body: Record<string, unknown> = {
    trace_id: traceId,
    score,
    user_id: userId,
    plan_id: planId,
  };
  if (conversationId !== null) body.conversation_id = conversationId;
  if (comment) body.comment = comment;
  await fetch(`${BASE}/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function approvePlan(
  planId: string,
  approverId = "ui_user"
): Promise<void> {
  const r = await fetch(`${BASE}/plans/${encodeURIComponent(planId)}/approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ approver_id: approverId, channel: "ui" }),
  });
  if (!r.ok && r.status !== 409) throw new Error(`HTTP ${r.status}`);
}

export async function rejectPlan(
  planId: string,
  reason = "",
  approverId = "ui_user"
): Promise<void> {
  const r = await fetch(`${BASE}/plans/${encodeURIComponent(planId)}/reject`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ approver_id: approverId, channel: "ui", reason }),
  });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
}

export async function getPlanStatus(planId: string): Promise<PlanStatus> {
  const r = await fetch(`${BASE}/plans/${encodeURIComponent(planId)}`);
  return r.json();
}

export function sourceUrl(filename: string): string {
  return `${BASE}/sources/${encodeURIComponent(filename)}`;
}

export function reportUrl(year: number, ext: "md" | "docx" | "pdf"): string {
  return `${BASE}/reports/${year}.${ext}`;
}

export async function uploadDocument(
  file: File,
  title?: string,
  year?: number,
  keywords?: string,
  documentCategory?: string,
): Promise<IngestResponse> {
  const form = new FormData();
  form.append("file", file, file.name);
  if (title) form.append("title", title);
  if (year !== undefined) form.append("year", String(year));
  if (keywords) form.append("keywords", keywords);
  if (documentCategory) form.append("document_category", documentCategory);
  const r = await fetch(`${BASE}/ingest`, { method: "POST", body: form });
  if (!r.ok) {
    const msg = await r.text().catch(() => `HTTP ${r.status}`);
    throw new Error(msg || `HTTP ${r.status}`);
  }
  return r.json() as Promise<IngestResponse>;
}
