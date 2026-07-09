import { useState } from "react";
import { approvePlan, rejectPlan } from "../api/client";
import { useCountdown } from "../hooks/useCountdown";
import { usePlanPolling } from "../hooks/usePlanPolling";
import type { ApprovalRequiredEvent } from "../api/types";

interface Props {
  event: ApprovalRequiredEvent;
  telegramConfigured: boolean;
  onApproved: () => void;
  onRejected: () => void;
}

type Mode = "telegram-watching" | "manual-form" | "reject-form";

export function ApprovalCard({ event, onApproved, onRejected }: Props) {
  const [mode, setMode] = useState<Mode>("telegram-watching");
  const [rejectReason, setRejectReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const countdown = useCountdown(event.expires_at);
  const status = usePlanPolling(event.plan_id, 5000);

  // Auto-detect Telegram approval
  if (status?.state === "approved") { onApproved(); }
  else if (status?.state === "rejected") { onRejected(); }

  const handleApprove = async () => {
    setBusy(true); setError(null);
    try { await approvePlan(event.plan_id); onApproved(); }
    catch (e) { setError(String(e)); }
    finally { setBusy(false); }
  };

  const handleReject = async () => {
    setBusy(true); setError(null);
    try { await rejectPlan(event.plan_id, rejectReason); onRejected(); }
    catch (e) { setError(String(e)); }
    finally { setBusy(false); }
  };

  const triggerLabel: Record<string, string> = {
    report: "Executive Report",
    kpi: "Large KPI Figure",
    "pre-execution": "Pre-Execution Gate",
  };

  return (
    <div style={{
      background: "linear-gradient(135deg,#fffbeb,#fef3c7)",
      border: "1px solid #f59e0b",
      borderRadius: 14,
      overflow: "hidden",
      boxShadow: "0 4px 16px rgba(245,158,11,.15)",
    }}>
      {/* Header */}
      <div style={{
        background: "linear-gradient(90deg,#f59e0b,#d97706)",
        padding: "10px 18px",
        display: "flex", alignItems: "center", justifyContent: "space-between",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 16 }}>⏸</span>
          <span style={{ color: "#fff", fontWeight: 700, fontSize: 14 }}>
            Manager Approval Required
          </span>
          <span style={{
            background: "rgba(255,255,255,.25)", color: "#fff",
            fontSize: 10, fontWeight: 700, padding: "2px 8px", borderRadius: 20,
          }}>
            {triggerLabel[event.trigger_case] ?? event.trigger_case}
          </span>
        </div>
        {countdown && (
          <span style={{ color: "rgba(255,255,255,.9)", fontSize: 12, fontWeight: 500 }}>
            ⏰ {countdown}
          </span>
        )}
      </div>

      {/* Body */}
      <div style={{ padding: "16px 18px" }}>
        <p style={{ fontSize: 13, color: "#92400e", lineHeight: 1.6, marginBottom: 14 }}>
          {event.message}
        </p>

        {error && (
          <div style={{
            background: "#fef2f2", border: "1px solid #fca5a5",
            borderRadius: 8, padding: "8px 12px",
            fontSize: 12, color: "#dc2626", marginBottom: 12,
          }}>{error}</div>
        )}

        {/* Telegram watching mode */}
        {mode === "telegram-watching" && (
          <>
            <div style={{
              background: "rgba(255,255,255,.65)",
              border: "1px solid #fde68a", borderRadius: 10,
              padding: "12px 14px", marginBottom: 14,
            }}>
              <div style={{ display: "flex", alignItems: "center", gap: 6, fontWeight: 600, fontSize: 12, color: "#78350f", marginBottom: 6 }}>
                <span>📱</span> Telegram notification sent
              </div>
              <div style={{ fontSize: 12, color: "#92400e", lineHeight: 1.6 }}>
                Send{" "}
                <code style={{ background: "#fef3c7", padding: "1px 6px", borderRadius: 4, fontFamily: "monospace", fontSize: 11 }}>
                  /approve {"<token>"}
                </code>{" "}
                or{" "}
                <code style={{ background: "#fef3c7", padding: "1px 6px", borderRadius: 4, fontFamily: "monospace", fontSize: 11 }}>
                  /reject {"<token>"}
                </code>{" "}
                in the bot
              </div>
              <div style={{ fontSize: 11, color: "#b45309", marginTop: 6 }}>
                ⏱ Checking every 5 s…
              </div>
            </div>

            <button
              onClick={() => setMode("manual-form")}
              style={{
                width: "100%",
                background: "rgba(255,255,255,.7)",
                border: "1.5px dashed #f59e0b",
                borderRadius: 10,
                color: "#78350f", fontWeight: 600, fontSize: 13,
                padding: "10px 0", cursor: "pointer",
                transition: "all .2s",
              }}
              onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.background = "rgba(255,255,255,.95)"; }}
              onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.background = "rgba(255,255,255,.7)"; }}
            >
              Approve or Reject here instead →
            </button>
          </>
        )}

        {/* Manual approve/reject form */}
        {mode === "manual-form" && (
          <>
            <p style={{ fontSize: 12, fontWeight: 600, color: "#78350f", marginBottom: 12 }}>
              Approve or Reject here
            </p>
            <div style={{ display: "flex", gap: 10, marginBottom: 10 }}>
              <button
                onClick={handleApprove}
                disabled={busy}
                style={{
                  flex: 1,
                  background: busy ? "#d1fae5" : "linear-gradient(135deg,#16a34a,#15803d)",
                  border: "none", borderRadius: 10,
                  color: "#fff", fontWeight: 700, fontSize: 13,
                  padding: "11px 0", cursor: busy ? "not-allowed" : "pointer",
                  boxShadow: busy ? "none" : "0 2px 8px rgba(22,163,74,.3)",
                }}
              >✅ Approve</button>
              <button
                onClick={() => setMode("reject-form")}
                disabled={busy}
                style={{
                  flex: 1,
                  background: "rgba(255,255,255,.7)",
                  border: "1px solid #fcd34d", borderRadius: 10,
                  color: "#92400e", fontWeight: 600, fontSize: 13,
                  padding: "11px 0", cursor: "pointer",
                }}
              >❌ Reject</button>
            </div>
            <button
              onClick={() => setMode("telegram-watching")}
              disabled={busy}
              style={{
                background: "none", border: "none", cursor: "pointer",
                fontSize: 12, color: "#b45309", fontWeight: 500,
                padding: "2px 0",
              }}
            >← Back to Telegram view</button>
          </>
        )}

        {/* Reject reason form */}
        {mode === "reject-form" && (
          <>
            <p style={{ fontSize: 12, fontWeight: 600, color: "#78350f", marginBottom: 8 }}>
              Rejection reason (optional):
            </p>
            <textarea
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              placeholder="Explain why this is being rejected…"
              rows={2}
              style={{
                width: "100%", resize: "none",
                border: "1px solid #fcd34d", borderRadius: 8,
                padding: "8px 12px", fontSize: 13,
                background: "rgba(255,255,255,.8)",
                color: "#1a1a2e", outline: "none", fontFamily: "inherit",
                marginBottom: 10,
              }}
            />
            <div style={{ display: "flex", gap: 10 }}>
              <button
                onClick={handleReject}
                disabled={busy}
                style={{
                  flex: 1,
                  background: "linear-gradient(135deg,#dc2626,#b91c1c)",
                  border: "none", borderRadius: 10,
                  color: "#fff", fontWeight: 700, fontSize: 13,
                  padding: "11px 0", cursor: busy ? "not-allowed" : "pointer",
                  boxShadow: "0 2px 8px rgba(220,38,38,.3)",
                }}
              >❌ Confirm Reject</button>
              <button
                onClick={() => setMode("manual-form")}
                disabled={busy}
                style={{
                  flex: 1,
                  background: "rgba(255,255,255,.7)",
                  border: "1px solid #fcd34d", borderRadius: 10,
                  color: "#78350f", fontWeight: 600, fontSize: 13,
                  padding: "11px 0", cursor: "pointer",
                }}
              >← Back</button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
