import { useEffect, useState } from "react";
import type { AdminAuditEvent, AdminConversation, AdminPlan, Message } from "../api/types";
import {
  adminGetAudit,
  adminGetConversations,
  adminGetPlans,
  getMessages,
} from "../api/client";

type AdminTab = "conversations" | "plans" | "audit";

const STATE_BADGE: Record<string, { bg: string; color: string }> = {
  suspended: { bg: "#fef3c7", color: "#d97706" },
  approved:  { bg: "#dcfce7", color: "#15803d" },
  rejected:  { bg: "#fee2e2", color: "#dc2626" },
};

function stateBadge(state: string) {
  const s = STATE_BADGE[state] ?? { bg: "#f4f4f5", color: "#52525b" };
  return (
    <span style={{
      fontSize: 11, fontWeight: 600, padding: "2px 8px", borderRadius: 20,
      background: s.bg, color: s.color,
    }}>{state}</span>
  );
}

function eventChip(eventType: string) {
  let bg = "#f4f4f5", color = "#52525b";
  if (eventType.startsWith("approval.")) { bg = "#fee2e2"; color = "#dc2626"; }
  else if (eventType.startsWith("rag.") || eventType.startsWith("supervisor.")) { bg = "#eff6ff"; color = "#1d4ed8"; }
  else if (eventType.startsWith("feedback.")) { bg = "#faf5ff"; color = "#7c3aed"; }
  else if (eventType.startsWith("planner.") || eventType.startsWith("orchestrator.")) { bg = "#fff7ed"; color = "#c2410c"; }
  return (
    <span style={{
      fontSize: 10, fontFamily: "monospace", fontWeight: 600,
      padding: "2px 7px", borderRadius: 6,
      background: bg, color,
    }}>{eventType}</span>
  );
}

export function AdminPage() {
  const [tab, setTab] = useState<AdminTab>("conversations");
  const [convs, setConvs] = useState<AdminConversation[]>([]);
  const [plans, setPlans] = useState<AdminPlan[]>([]);
  const [audit, setAudit] = useState<AdminAuditEvent[]>([]);
  const [loading, setLoading] = useState(false);
  const [expandedConvId, setExpandedConvId] = useState<number | null>(null);
  const [convMessages, setConvMessages] = useState<Record<number, Message[]>>({});

  const refresh = async () => {
    setLoading(true);
    try {
      const [c, p, a] = await Promise.all([
        adminGetConversations(),
        adminGetPlans(),
        adminGetAudit(),
      ]);
      setConvs(c);
      setPlans(p);
      setAudit(a);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void refresh(); }, []);

  const toggleConv = async (id: number) => {
    if (expandedConvId === id) { setExpandedConvId(null); return; }
    setExpandedConvId(id);
    if (!convMessages[id]) {
      const msgs = await getMessages(id);
      setConvMessages((prev) => ({ ...prev, [id]: msgs }));
    }
  };

  const fmtDate = (iso: string) => new Date(iso).toLocaleString(undefined, {
    month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
  });

  // --- shared table styles ---
  const thStyle: React.CSSProperties = {
    padding: "8px 12px", textAlign: "left",
    fontSize: 11, fontWeight: 700, textTransform: "uppercase",
    letterSpacing: ".05em", color: "var(--text-muted)",
    borderBottom: "2px solid var(--border)",
    background: "#fafafa",
    whiteSpace: "nowrap",
  };
  const tdStyle: React.CSSProperties = {
    padding: "9px 12px", fontSize: 13,
    borderBottom: "1px solid var(--border)",
    color: "var(--text-primary)",
    verticalAlign: "top",
  };

  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", minHeight: 0, background: "var(--bg-page)" }}>
      {/* Header bar */}
      <div style={{
        padding: "14px 24px", borderBottom: "1px solid var(--border)",
        background: "var(--bg-card)",
        display: "flex", alignItems: "center", gap: 12,
      }}>
        <span style={{ fontWeight: 700, fontSize: 15, color: "var(--text-primary)" }}>🗄️ Admin</span>
        <span style={{ opacity: .3 }}>|</span>
        {/* Tabs */}
        {(["conversations", "plans", "audit"] as AdminTab[]).map((t) => (
          <button key={t} onClick={() => setTab(t)} style={{
            background: tab === t ? "rgba(0,48,135,.08)" : "transparent",
            border: "none", cursor: "pointer",
            padding: "4px 10px", borderRadius: 8,
            fontWeight: tab === t ? 600 : 400,
            fontSize: 13,
            color: tab === t ? "var(--brand)" : "var(--text-secondary)",
          }}>
            {t === "conversations" ? "Conversations" : t === "plans" ? "Plans" : "Audit Log"}
          </button>
        ))}
        <button onClick={() => void refresh()} disabled={loading} style={{
          marginLeft: "auto",
          background: "none", border: "1px solid var(--border)", borderRadius: 8,
          padding: "5px 14px", cursor: "pointer", fontSize: 12,
          color: "var(--text-secondary)",
          opacity: loading ? .5 : 1,
        }}>
          {loading ? "Loading…" : "↻ Refresh"}
        </button>
      </div>

      {/* Content */}
      <div style={{ flex: 1, overflowY: "auto", padding: "20px 24px" }}>

        {/* CONVERSATIONS TAB */}
        {tab === "conversations" && (
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr>
                <th style={thStyle}>ID</th>
                <th style={thStyle}>User</th>
                <th style={thStyle}>Title</th>
                <th style={thStyle}>Messages</th>
                <th style={thStyle}>Created</th>
              </tr>
            </thead>
            <tbody>
              {convs.map((conv) => {
                const isExpanded = expandedConvId === conv.id;
                const msgs = convMessages[conv.id];
                return (
                  <>
                    <tr
                      key={conv.id}
                      onClick={() => void toggleConv(conv.id)}
                      style={{ cursor: "pointer" }}
                      onMouseEnter={(e) => { (e.currentTarget as HTMLTableRowElement).style.background = "#f9fafb"; }}
                      onMouseLeave={(e) => { (e.currentTarget as HTMLTableRowElement).style.background = "transparent"; }}
                    >
                      <td style={{ ...tdStyle, fontFamily: "monospace", fontSize: 12 }}>{conv.id}</td>
                      <td style={tdStyle}>{conv.user_id}</td>
                      <td style={{ ...tdStyle, maxWidth: 260 }}>
                        <span style={{ opacity: conv.title ? 1 : .4 }}>
                          {conv.title ?? "(untitled)"}
                        </span>
                      </td>
                      <td style={{ ...tdStyle, textAlign: "center" }}>{conv.message_count}</td>
                      <td style={{ ...tdStyle, color: "var(--text-secondary)", whiteSpace: "nowrap" }}>
                        {fmtDate(conv.created_at)}
                      </td>
                    </tr>
                    {isExpanded && (
                      <tr key={`${conv.id}-expanded`}>
                        <td colSpan={5} style={{ padding: "0 0 0 32px", background: "#f8fafc", borderBottom: "1px solid var(--border)" }}>
                          <div style={{ padding: "12px 16px 12px 0" }}>
                            {!msgs ? (
                              <span style={{ fontSize: 12, color: "var(--text-muted)" }}>Loading messages…</span>
                            ) : msgs.length === 0 ? (
                              <span style={{ fontSize: 12, color: "var(--text-muted)" }}>No messages yet.</span>
                            ) : (
                              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                                {msgs.map((msg) => (
                                  <div key={msg.id} style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
                                    <span style={{
                                      flexShrink: 0,
                                      fontSize: 10, fontWeight: 700,
                                      padding: "2px 7px", borderRadius: 12,
                                      background: msg.role === "user" ? "#fee2e2" : "#f4f4f5",
                                      color: msg.role === "user" ? "#dc2626" : "#52525b",
                                    }}>{msg.role}</span>
                                    <span style={{ fontSize: 12, color: "var(--text-primary)", flex: 1 }}>
                                      {msg.content.slice(0, 120)}{msg.content.length > 120 ? "…" : ""}
                                    </span>
                                    <span style={{ flexShrink: 0, fontSize: 11, color: "var(--text-muted)", whiteSpace: "nowrap" }}>
                                      {fmtDate(msg.created_at)}
                                    </span>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        </td>
                      </tr>
                    )}
                  </>
                );
              })}
            </tbody>
          </table>
        )}

        {/* PLANS TAB */}
        {tab === "plans" && (
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr>
                <th style={thStyle}>Plan ID</th>
                <th style={thStyle}>User</th>
                <th style={thStyle}>Conv</th>
                <th style={thStyle}>State</th>
                <th style={thStyle}>Trigger</th>
                <th style={thStyle}>Created</th>
                <th style={thStyle}>Updated</th>
              </tr>
            </thead>
            <tbody>
              {plans.map((plan) => (
                <tr
                  key={plan.id}
                  onMouseEnter={(e) => { (e.currentTarget as HTMLTableRowElement).style.background = "#f9fafb"; }}
                  onMouseLeave={(e) => { (e.currentTarget as HTMLTableRowElement).style.background = "transparent"; }}
                >
                  <td style={{ ...tdStyle, fontFamily: "monospace", fontSize: 12 }}
                    title={plan.id}
                  >
                    {plan.id.slice(0, 8)}…
                  </td>
                  <td style={tdStyle}>{plan.user_id}</td>
                  <td style={{ ...tdStyle, fontFamily: "monospace", fontSize: 12, color: "var(--text-secondary)" }}>
                    {plan.conversation_id ?? "—"}
                  </td>
                  <td style={tdStyle}>{stateBadge(plan.state)}</td>
                  <td style={{ ...tdStyle, color: "var(--text-secondary)", fontSize: 12 }}>
                    {plan.trigger_case ?? "—"}
                  </td>
                  <td style={{ ...tdStyle, color: "var(--text-secondary)", whiteSpace: "nowrap" }}>
                    {fmtDate(plan.created_at)}
                  </td>
                  <td style={{ ...tdStyle, color: "var(--text-secondary)", whiteSpace: "nowrap" }}>
                    {fmtDate(plan.updated_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {/* AUDIT TAB */}
        {tab === "audit" && (
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr>
                <th style={thStyle}>#</th>
                <th style={thStyle}>Time</th>
                <th style={thStyle}>User</th>
                <th style={thStyle}>Event Type</th>
                <th style={thStyle}>Conv</th>
                <th style={thStyle}>Payload</th>
              </tr>
            </thead>
            <tbody>
              {audit.map((event) => {
                const payloadStr = JSON.stringify(event.payload);
                const payloadSnippet = payloadStr.length > 80 ? payloadStr.slice(0, 80) + "…" : payloadStr;
                return (
                  <tr
                    key={event.id}
                    onMouseEnter={(e) => { (e.currentTarget as HTMLTableRowElement).style.background = "#f9fafb"; }}
                    onMouseLeave={(e) => { (e.currentTarget as HTMLTableRowElement).style.background = "transparent"; }}
                  >
                    <td style={{ ...tdStyle, fontFamily: "monospace", fontSize: 12, color: "var(--text-muted)" }}>
                      {event.id}
                    </td>
                    <td style={{ ...tdStyle, whiteSpace: "nowrap", color: "var(--text-secondary)" }}>
                      {fmtDate(event.ts)}
                    </td>
                    <td style={tdStyle}>{event.user_id}</td>
                    <td style={tdStyle}>{eventChip(event.event_type)}</td>
                    <td style={{ ...tdStyle, fontFamily: "monospace", fontSize: 12, color: "var(--text-secondary)" }}>
                      {event.conversation_id ?? "—"}
                    </td>
                    <td style={{ ...tdStyle, fontFamily: "monospace", fontSize: 11, color: "var(--text-secondary)", maxWidth: 320 }}
                      title={payloadStr}
                    >
                      {payloadSnippet}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}

      </div>
    </div>
  );
}
