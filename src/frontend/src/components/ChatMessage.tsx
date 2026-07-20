import React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Turn } from "../store/chatStore";
import { AudioPlayer } from "./AudioPlayer";
import { CitationPanel } from "./CitationPanel";
import { FeedbackButtons } from "./FeedbackButtons";
import { OperationExpander } from "./OperationExpander";
import { PipelineStepper } from "./PipelineStepper";
import { ReportDownloads } from "./ReportDownloads";

const formatTime = (iso: string | null): string | null => {
  if (!iso) return null;
  return new Date(iso).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
};

const ShieldAvatar = () => (
  <div style={{
    width: 34, height: 34, flexShrink: 0,
    background: "linear-gradient(135deg,#fb7185,#e11d48)",
    borderRadius: 10,
    display: "flex", alignItems: "center", justifyContent: "center",
    fontSize: 17, boxShadow: "0 2px 8px rgba(244,63,94,.35)",
    marginTop: 2,
  }}>🛡️</div>
);

const COLOR_KEYWORDS: Record<string, string> = {
  green: "#16a34a",
  amber: "#d97706",
  red:   "#dc2626",
};

function colorizeText(text: string): React.ReactNode {
  const parts = text.split(/(\bgreen\b|\bamber\b|\bred\b)/gi);
  if (parts.length === 1) return text;
  return parts.map((part, i) => {
    const color = COLOR_KEYWORDS[part.toLowerCase()];
    return color
      ? <span key={i} style={{ color, fontWeight: 700 }}>{part}</span>
      : part;
  });
}

function colorizeChildren(children: React.ReactNode): React.ReactNode {
  if (typeof children === "string") return colorizeText(children);
  if (Array.isArray(children)) return children.map((c, i) =>
    typeof c === "string" ? <React.Fragment key={i}>{colorizeText(c)}</React.Fragment> : c
  );
  return children;
}

interface Props {
  turn: Turn;
  turnIndex: number;
  conversationId: number | null;
  userId: string;
  ratedTurns: Set<string>;
  hasPendingApproval: boolean;
  voiceEnabled?: boolean;
  voiceLanguage?: string;
  onRated: (key: string) => void;
}

export function ChatMessage({
  turn,
  turnIndex,
  conversationId,
  userId,
  ratedTurns,
  hasPendingApproval,
  voiceEnabled,
  voiceLanguage,
  onRated,
}: Props) {
  const turnKey = `${conversationId}_${turnIndex}`;

  if (turn.role === "user") {
    const sentAt = formatTime(turn.completedAt);
    return (
      <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", padding: "2px 0", gap: 3 }}>
        <div style={{
          maxWidth: "72%",
          background: "linear-gradient(135deg,#f43f5e,#e11d48)",
          color: "#fff",
          borderRadius: "18px 18px 4px 18px",
          padding: "12px 18px",
          fontSize: 14, lineHeight: 1.6,
          boxShadow: "0 2px 10px rgba(244,63,94,.3)",
        }}>
          {turn.content}
        </div>
        {sentAt && (
          <span style={{ fontSize: 10, color: "var(--text-muted)", paddingRight: 4 }}>{sentAt}</span>
        )}
      </div>
    );
  }

  return (
    <div style={{ display: "flex", gap: 12, padding: "2px 0", alignItems: "flex-start" }}>
      <ShieldAvatar />
      <div style={{ flex: 1, minWidth: 0 }}>
        {/* Answer bubble */}
        <div style={{
          background: "var(--bg-card)",
          border: "1px solid var(--border)",
          borderRadius: "4px 18px 18px 18px",
          padding: "14px 18px",
          boxShadow: "var(--shadow-sm)",
          fontSize: 14, lineHeight: 1.65,
          color: "var(--text-primary)",
        }}>
          <div className="prose">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              urlTransform={(url) => url}
              components={{
                // Pass data: URIs through; show a badge for any other broken src
                img: ({ src, alt }) =>
                  src && src.startsWith("data:") ? (
                    <img
                      src={src}
                      alt={alt ?? "Chart"}
                      style={{ maxWidth: "100%", borderRadius: 8, margin: "8px 0", display: "block" }}
                    />
                  ) : (
                    <span style={{
                      display: "inline-flex", alignItems: "center", gap: 5,
                      background: "#f4f4f5", border: "1px solid var(--border)",
                      borderRadius: 6, padding: "3px 10px",
                      fontSize: 11, color: "var(--text-muted)",
                    }}>📊 {alt ?? "Chart"}</span>
                  ),
                // Colorize green / amber / red keywords inside table cells
                td: ({ children }) => <td>{colorizeChildren(children)}</td>,
              }}
            >
              {turn.content}
            </ReactMarkdown>
          </div>
          {turn.isStreaming && turn.content.length === 0 && (
            <span style={{ color: "var(--text-muted)", fontSize: 13 }}>Thinking…</span>
          )}
          {turn.isStreaming && (
            <span className="cursor-blink" style={{
              display: "inline-block", width: 2, height: 14,
              background: "var(--brand)", marginLeft: 2, verticalAlign: "middle",
            }} />
          )}
        </div>

        {/* Pipeline stepper — shown during AND after streaming */}
        {Object.keys(turn.stages).length > 0 && (
          <div style={{ marginTop: 6, paddingLeft: 2 }}>
            <PipelineStepper
              stages={turn.stages}
              skillLabels={turn.skillLabels}
              route={turn.route}
              isStreaming={turn.isStreaming}
              reformulatedQuery={turn.reformulatedQuery}
            />
          </div>
        )}

        {/* Sub-content — only after streaming completes */}
        {!turn.isStreaming && (
          <div style={{ paddingLeft: 2 }}>
            {(turn.totalMs !== null || turn.completedAt !== null) && (
              <div style={{
                display: "flex", alignItems: "center", gap: 10,
                marginTop: 5, marginBottom: 2,
                fontSize: 10, color: "var(--text-muted)",
                fontVariantNumeric: "tabular-nums",
              }}>
                {formatTime(turn.completedAt) && (
                  <>
                    <span>{formatTime(turn.completedAt)}</span>
                    {turn.totalMs !== null && <span style={{ opacity: .4 }}>·</span>}
                  </>
                )}
                {turn.totalMs !== null && (
                  <>
                    <span title="Time to first token">
                      ⚡ TTFT {turn.ttftMs !== null ? (turn.ttftMs / 1000).toFixed(2) : "—"}s
                    </span>
                    <span style={{ opacity: .4 }}>·</span>
                    <span title="Total completion time">
                      ⏱ Total {(turn.totalMs / 1000).toFixed(2)}s
                    </span>
                  </>
                )}
              </div>
            )}
            <CitationPanel citations={turn.citations} />
            <ReportDownloads reportYear={turn.reportYear} reportKind={turn.reportKind} />
            <OperationExpander dataOperation={turn.dataOperation} route={turn.route} />
            {!hasPendingApproval && turn.content.trim() && (
              <FeedbackButtons
                planId={turn.planId}
                conversationId={conversationId}
                userId={userId}
                turnKey={turnKey}
                onRated={onRated}
                alreadyRated={ratedTurns.has(turnKey)}
              />
            )}
            {voiceEnabled && turn.content.trim() && (
              <AudioPlayer text={turn.content} language={voiceLanguage} />
            )}
          </div>
        )}
      </div>
    </div>
  );
}
