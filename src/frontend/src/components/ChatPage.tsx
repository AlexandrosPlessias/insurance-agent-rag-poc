import { useEffect, useRef } from "react";
import { getMessages, streamChat, streamPlanResume } from "../api/client";
import type { Turn } from "../store/chatStore";
import type { DoneEvent, NDJSONEvent, StageEvent } from "../api/types";
import { useChatStore } from "../store/chatStore";
import { ApprovalCard } from "./ApprovalCard";
import { ChatInput } from "./ChatInput";
import { ChatMessage } from "./ChatMessage";
import { EmptyState } from "./EmptyState";

interface Props {
  conversationId: number | null;
  userId: string;
  telegramConfigured: boolean;
  onConversationCreated: (id: number) => void;
}

export function ChatPage({
  conversationId,
  userId,
  telegramConfigured,
  onConversationCreated,
}: Props) {
  const { state, dispatch } = useChatStore();
  const bottomRef = useRef<HTMLDivElement>(null);
  const requestedAtRef = useRef<number | null>(null);
  const firstTokenAtRef = useRef<number | null>(null);
  const streamAbortRef = useRef<AbortController | null>(null);
  // Tracks the current conversationId prop so processStream can read it asynchronously.
  // Used to guard SET_CONVERSATION_ID: only dispatch when still in a new-conv context (null).
  const conversationIdRef = useRef(conversationId);
  useEffect(() => { conversationIdRef.current = conversationId; }, [conversationId]);
  const isStreaming = state.history.some((t) => t.isStreaming);

  // Keep sessionStorage cache up-to-date after each turn completes.
  // This ensures approval-resumed answers are persisted even though the
  // resume route never saves messages to the DB.
  useEffect(() => {
    if (!state.conversationId) return;
    const done = state.history.filter((t) => !t.isStreaming);
    if (!done.length) return;
    try {
      sessionStorage.setItem(`turns_v1_${state.conversationId}`, JSON.stringify(done));
    } catch {}
  }, [state.history, state.conversationId]);

  // Load message history when switching to an existing conversation.
  // Tries sessionStorage first (preserves approval flows not saved to DB),
  // then falls back to getMessages().
  useEffect(() => {
    if (!conversationId || state.history.length > 0) return;

    const cacheKey = `turns_v1_${conversationId}`;
    const cached = sessionStorage.getItem(cacheKey);
    if (cached) {
      try {
        const turns = JSON.parse(cached) as Turn[];
        if (turns.length > 0) {
          dispatch({ type: "LOAD_HISTORY", turns });
          return;
        }
      } catch {}
    }

    getMessages(conversationId).then((msgs) => {
      if (msgs.length === 0) return;
      const turns: Turn[] = msgs.map((m) => ({
        role: m.role as "user" | "assistant",
        content: m.content,
        citations: m.citations ?? [],
        route: m.route ?? "",
        stages: {},
        skillLabels: {},
        planId: null,
        reformulatedQuery: null,
        dataOperation: null,
        reportKind: null,
        reportYear: null,
        reportRunId: null,
        validated: false,
        isStreaming: false,
        completedAt: null,
        ttftMs: null,
        totalMs: null,
      }));
      dispatch({ type: "LOAD_HISTORY", turns });
    }).catch(() => {});
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conversationId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [state.history.length, state.history[state.history.length - 1]?.content]);

  const processStream = async (gen: AsyncGenerator<NDJSONEvent>) => {
    for await (const event of gen) {
      switch (event.type) {
        case "conversation":
          // Only assign the new conv ID when we're still in the new-conversation context
          // (conversationIdRef.current === null). If the user navigated away before this
          // event arrived the ref is already the new conversation's ID — skip the dispatch
          // so the stale stream doesn't corrupt state.conversationId.
          if (conversationIdRef.current === null) {
            dispatch({ type: "SET_CONVERSATION_ID", conversationId: event.conversation_id });
          }
          onConversationCreated(event.conversation_id);
          break;
        case "stage": {
          const se = event as StageEvent;
          dispatch({
            type: "UPDATE_STAGE",
            node: se.node,
            status: se.status === "started" ? "running" : "done",
          });
          if (se.status === "started" && se.info?.startsWith("skill=")) {
            dispatch({
              type: "UPDATE_SKILL_LABEL",
              node: se.node,
              skillId: se.info.slice("skill=".length),
            });
          }
          break;
        }
        case "token":
          if (firstTokenAtRef.current === null && requestedAtRef.current !== null) {
            firstTokenAtRef.current = Date.now();
          }
          dispatch({ type: "APPEND_TOKEN", value: event.value });
          break;
        case "meta":
          dispatch({ type: "SET_META", reformulatedQuery: event.reformulated_query });
          break;
        case "done":
          dispatch({ type: "FINALIZE_TURN", event: event as DoneEvent });
          if (requestedAtRef.current !== null) {
            dispatch({
              type: "SET_TURN_TIMING",
              ttftMs: firstTokenAtRef.current !== null
                ? firstTokenAtRef.current - requestedAtRef.current
                : null,
              totalMs: Date.now() - requestedAtRef.current,
            });
          }
          break;
        case "approval_required":
          // Stamp a message into the gate turn before closing it, so the bubble
          // is never empty. Resume will push a separate fresh assistant turn.
          dispatch({ type: "APPEND_TOKEN", value: "⏸ Plan submitted for manager approval…" });
          dispatch({ type: "CLOSE_STREAMING_TURN" });
          dispatch({ type: "SET_PENDING_APPROVAL", event });
          break;
        case "error":
          dispatch({ type: "SET_STREAM_ERROR", error: event.value });
          break;
      }
    }
  };

  const handleSubmit = async (text: string) => {
    streamAbortRef.current?.abort();
    const controller = new AbortController();
    streamAbortRef.current = controller;
    requestedAtRef.current = Date.now();
    firstTokenAtRef.current = null;
    dispatch({ type: "PUSH_USER_TURN", content: text });
    dispatch({ type: "PUSH_ASSISTANT_TURN" });
    try {
      const lastDataOp = [...state.history]
        .reverse()
        .find((t) => t.role === "assistant" && t.route === "data" && t.dataOperation)
        ?.dataOperation ?? undefined;
      await processStream(
        streamChat(
          { question: text, user_id: userId, conversation_id: conversationId, last_data_operation: lastDataOp },
          controller.signal,
        )
      );
    } catch (e) {
      if (controller.signal.aborted) return;
      dispatch({ type: "CLOSE_STREAMING_TURN" });
      dispatch({ type: "SET_STREAM_ERROR", error: String(e) });
    }
  };

  const handleApproved = async () => {
    const planId = state.pendingApproval?.plan_id;
    if (!planId) return;
    streamAbortRef.current?.abort();
    const controller = new AbortController();
    streamAbortRef.current = controller;
    requestedAtRef.current = Date.now();
    firstTokenAtRef.current = null;
    dispatch({ type: "CLEAR_PENDING_APPROVAL", resolution: "✅ Plan approved — resuming execution…" });
    dispatch({ type: "PUSH_ASSISTANT_TURN" });
    try {
      await processStream(streamPlanResume(planId, controller.signal));
    } catch (e) {
      if (controller.signal.aborted) return;
      dispatch({ type: "CLOSE_STREAMING_TURN" });
      dispatch({ type: "SET_STREAM_ERROR", error: String(e) });
    }
  };

  const handleRejected = () => {
    dispatch({ type: "CLEAR_PENDING_APPROVAL", resolution: "❌ Request declined by manager." });
    dispatch({ type: "PUSH_ASSISTANT_TURN" });
    dispatch({ type: "APPEND_TOKEN", value: "The request was declined by the manager." });
    dispatch({
      type: "FINALIZE_TURN",
      event: {
        type: "done",
        citations: [],
        validated: false,
        retry_count: 0,
        critique: "",
        route: "decline",
        target_year: null,
        plan_id: state.pendingApproval?.plan_id ?? null,
        data_operation: null,
        report_kind: null,
        report_year: null,
        report_run_id: null,
      },
    });
  };

  const isEmpty = state.history.length === 0 && !state.pendingApproval;

  return (
    <div style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0 }}>
      {/* Scrollable message area */}
      <div style={{ flex: 1, overflowY: "auto", padding: "24px 24px 16px" }}>
        {isEmpty ? (
          <EmptyState onPrompt={handleSubmit} />
        ) : (
          <div style={{ maxWidth: 760, margin: "0 auto", display: "flex", flexDirection: "column", gap: 16 }}>
            {state.history.map((turn, i) => {
              // Hide any completed assistant turn with no content (stale/error turn)
              if (turn.role === "assistant" && !turn.isStreaming && !turn.content.trim()) return null;
              return (
                <ChatMessage
                  key={i}
                  turn={turn}
                  turnIndex={i}
                  conversationId={state.conversationId}
                  userId={userId}
                  ratedTurns={state.ratedTurns}
                  hasPendingApproval={
                    state.pendingApproval !== null && i === state.history.length - 1
                  }
                  onRated={(key) => dispatch({ type: "RATE_TURN", key })}
                />
              );
            })}

            {state.pendingApproval && (
              <ApprovalCard
                event={state.pendingApproval}
                telegramConfigured={telegramConfigured}
                onApproved={handleApproved}
                onRejected={handleRejected}
              />
            )}

            {state.streamError && (
              <div style={{
                background: "#fef2f2", border: "1px solid #fca5a5",
                borderRadius: 10, padding: "12px 16px",
                fontSize: 13, color: "#dc2626",
                display: "flex", alignItems: "center", gap: 10,
              }}>
                <span>⚠️</span>
                <span style={{ flex: 1 }}>{state.streamError}</span>
                <button
                  onClick={() => dispatch({ type: "CLEAR_STREAM_ERROR" })}
                  style={{
                    background: "none", border: "none", cursor: "pointer",
                    color: "#dc2626", fontSize: 18, lineHeight: 1,
                  }}
                >×</button>
              </div>
            )}

            <div ref={bottomRef} />
          </div>
        )}
      </div>

      {/* Input bar */}
      <div style={{
        padding: "12px 24px 18px",
        background: "var(--bg-page)",
        borderTop: "1px solid var(--border)",
      }}>
        <div style={{ maxWidth: 760, margin: "0 auto" }}>
          <ChatInput onSubmit={handleSubmit} disabled={isStreaming} />
          <p style={{
            textAlign: "center", fontSize: 11,
            color: "var(--text-muted)", marginTop: 8,
          }}>
            AI responses may contain errors. Always verify important information.
          </p>
        </div>
      </div>
    </div>
  );
}
