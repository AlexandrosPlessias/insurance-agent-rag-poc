import { createContext, useContext } from "react";
import type { ApprovalRequiredEvent, Citation, DoneEvent } from "../api/types";

export type StageStatus = "pending" | "running" | "done" | "off_path";

export interface Turn {
  role: "user" | "assistant";
  content: string;
  citations: Citation[];
  route: string;
  intent: string | null;
  effectiveResponseMode: "fast" | "accurate" | null;
  stages: Record<string, StageStatus>;
  skillLabels: Record<string, string>;
  planId: string | null;
  reformulatedQuery: string | null;
  dataOperation: unknown | null;
  reportKind: string | null;
  reportYear: number | null;
  reportRunId: string | null;
  validated: boolean;
  isStreaming: boolean;
  completedAt: string | null;
  ttftMs: number | null;
  totalMs: number | null;
}

export interface ChatState {
  conversationId: number | null;
  history: Turn[];
  pendingApproval: ApprovalRequiredEvent | null;
  ratedTurns: Set<string>;
  streamError: string | null;
}

type Action =
  | { type: "SET_CONVERSATION_ID"; conversationId: number }
  | { type: "PUSH_USER_TURN"; content: string }
  | { type: "PUSH_ASSISTANT_TURN" }
  | { type: "CLOSE_STREAMING_TURN" }
  | { type: "APPEND_TOKEN"; value: string }
  | { type: "UPDATE_STAGE"; node: string; status: StageStatus }
  | { type: "UPDATE_SKILL_LABEL"; node: string; skillId: string }
  | { type: "SET_META"; reformulatedQuery: string }
  | { type: "FINALIZE_TURN"; event: DoneEvent }
  | { type: "SET_PENDING_APPROVAL"; event: ApprovalRequiredEvent }
  | { type: "CLEAR_PENDING_APPROVAL"; resolution?: string }
  | { type: "RATE_TURN"; key: string }
  | { type: "SET_STREAM_ERROR"; error: string }
  | { type: "CLEAR_STREAM_ERROR" }
  | { type: "RESET"; conversationId: number | null }
  | { type: "LOAD_HISTORY"; turns: Turn[] }
  | { type: "SET_TURN_TIMING"; ttftMs: number | null; totalMs: number };

function emptyAssistantTurn(): Turn {
  return {
    role: "assistant",
    content: "",
    citations: [],
    route: "",
    intent: null,
    effectiveResponseMode: null,
    stages: {},
    skillLabels: {},
    planId: null,
    reformulatedQuery: null,
    dataOperation: null,
    reportKind: null,
    reportYear: null,
    reportRunId: null,
    validated: false,
    isStreaming: true,
    completedAt: null,
    ttftMs: null,
    totalMs: null,
  };
}

function chatReducer(state: ChatState, action: Action): ChatState {
  switch (action.type) {
    case "SET_CONVERSATION_ID":
      return { ...state, conversationId: action.conversationId };

    case "PUSH_USER_TURN":
      return {
        ...state,
        history: [
          ...state.history,
          {
            role: "user",
            content: action.content,
            citations: [],
            route: "",
            intent: null,
            effectiveResponseMode: null,
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
            completedAt: new Date().toISOString(),
            ttftMs: null,
            totalMs: null,
          },
        ],
        streamError: null,
      };

    case "PUSH_ASSISTANT_TURN":
      return { ...state, history: [...state.history, emptyAssistantTurn()] };

    case "CLOSE_STREAMING_TURN": {
      const history = [...state.history];
      const last = history[history.length - 1];
      if (!last || last.role !== "assistant") return state;
      // Coerce any still-running stages to done so the UI never shows
      // a red spinner on a gate turn where the backend suspended early.
      const closedStages = Object.fromEntries(
        Object.entries(last.stages).map(([k, v]) => [k, v === "running" ? "done" : v])
      ) as Record<string, StageStatus>;
      history[history.length - 1] = { ...last, isStreaming: false, stages: closedStages, completedAt: new Date().toISOString() };
      return { ...state, history };
    }

    case "APPEND_TOKEN": {
      const history = [...state.history];
      const last = history[history.length - 1];
      if (!last || last.role !== "assistant") return state;
      history[history.length - 1] = { ...last, content: last.content + action.value };
      return { ...state, history };
    }

    case "UPDATE_STAGE": {
      const history = [...state.history];
      const last = history[history.length - 1];
      if (!last || last.role !== "assistant") return state;
      history[history.length - 1] = {
        ...last,
        stages: { ...last.stages, [action.node]: action.status },
      };
      return { ...state, history };
    }

    case "UPDATE_SKILL_LABEL": {
      const history = [...state.history];
      const last = history[history.length - 1];
      if (!last || last.role !== "assistant") return state;
      history[history.length - 1] = {
        ...last,
        skillLabels: { ...last.skillLabels, [action.node]: action.skillId },
      };
      return { ...state, history };
    }

    case "SET_META": {
      const history = [...state.history];
      const last = history[history.length - 1];
      if (!last || last.role !== "assistant") return state;
      history[history.length - 1] = {
        ...last,
        reformulatedQuery: action.reformulatedQuery,
      };
      return { ...state, history };
    }

    case "FINALIZE_TURN": {
      const ev = action.event;
      const history = [...state.history];
      const last = history[history.length - 1];
      if (!last || last.role !== "assistant") return state;
      history[history.length - 1] = {
        ...last,
        citations: ev.citations ?? [],
        route: ev.route ?? "",
        intent: ev.intent ?? null,
        effectiveResponseMode: ev.effective_response_mode ?? null,
        planId: ev.plan_id ?? null,
        dataOperation: ev.data_operation ?? null,
        reportKind: ev.report_kind ?? null,
        reportYear: ev.report_year ?? null,
        reportRunId: ev.report_run_id ?? null,
        validated: ev.validated ?? false,
        isStreaming: false,
        completedAt: new Date().toISOString(),
      };
      return { ...state, history };
    }

    case "SET_PENDING_APPROVAL":
      return { ...state, pendingApproval: action.event };

    case "CLEAR_PENDING_APPROVAL": {
      if (!action.resolution) return { ...state, pendingApproval: null };
      // Update the last closed assistant turn (the gate turn) with a resolution message.
      const history = [...state.history];
      for (let i = history.length - 1; i >= 0; i--) {
        if (history[i].role === "assistant" && !history[i].isStreaming) {
          history[i] = { ...history[i], content: action.resolution };
          break;
        }
      }
      return { ...state, pendingApproval: null, history };
    }

    case "RATE_TURN":
      return { ...state, ratedTurns: new Set([...state.ratedTurns, action.key]) };

    case "SET_STREAM_ERROR":
      return { ...state, streamError: action.error };

    case "CLEAR_STREAM_ERROR":
      return { ...state, streamError: null };

    case "RESET":
      return {
        conversationId: action.conversationId,
        history: [],
        pendingApproval: null,
        ratedTurns: new Set(),
        streamError: null,
      };

    case "LOAD_HISTORY":
      return { ...state, history: action.turns };

    case "SET_TURN_TIMING": {
      const history = [...state.history];
      const last = history[history.length - 1];
      if (!last || last.role !== "assistant") return state;
      history[history.length - 1] = {
        ...last,
        ttftMs: action.ttftMs,
        totalMs: action.totalMs,
      };
      return { ...state, history };
    }

    default:
      return state;
  }
}

const initialState: ChatState = {
  conversationId: null,
  history: [],
  pendingApproval: null,
  ratedTurns: new Set(),
  streamError: null,
};

export const ChatContext = createContext<{
  state: ChatState;
  dispatch: React.Dispatch<Action>;
} | null>(null);

export function useChatStore() {
  const ctx = useContext(ChatContext);
  if (!ctx) throw new Error("useChatStore must be used inside ChatProvider");
  return ctx;
}

export { chatReducer, initialState };
export type { Action };
