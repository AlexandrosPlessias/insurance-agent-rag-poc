import { useEffect, useReducer, useState } from "react";
import { getHealth } from "../api/client";
import { ChatContext, chatReducer, initialState } from "../store/chatStore";
import { AdminPage } from "./AdminPage";
import { ChatPage } from "./ChatPage";
import { ConversationList } from "./ConversationList";
import { DocumentUpload } from "./DocumentUpload";

const TELEGRAM_CONFIGURED = Boolean(import.meta.env.VITE_TELEGRAM_CONFIGURED);

type ServiceState = "ok" | "down" | "inactive";

interface ServiceRow {
  label: string;
  detail?: string;
  state: ServiceState;
}

const DOT: Record<ServiceState, { color: string; glow?: string }> = {
  ok:       { color: "#22c55e", glow: "#22c55e" },
  down:     { color: "#f43f5e", glow: "#f43f5e" },
  inactive: { color: "#52525b" },
};

const TAG: Record<ServiceState, { color: string; label: string }> = {
  ok:       { color: "#86efac", label: "OK" },
  down:     { color: "#fda4af", label: "Down" },
  inactive: { color: "#52525b", label: "Inactive" },
};

function ServiceStatusRow({ label, detail, state }: ServiceRow) {
  const dot = DOT[state];
  const tag = TAG[state];
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "3px 0" }}>
      <div style={{
        width: 6, height: 6, borderRadius: "50%", flexShrink: 0,
        background: dot.color,
        boxShadow: dot.glow ? `0 0 5px ${dot.glow}` : "none",
      }} />
      <span style={{ flex: 1, fontSize: 11, color: "var(--sidebar-text)" }}>
        {label}
        {detail && <span style={{ opacity: .55, fontSize: 10, marginLeft: 4 }}>{detail}</span>}
      </span>
      <span style={{ fontSize: 10, fontWeight: 600, color: tag.color }}>{tag.label}</span>
    </div>
  );
}

export function AppShell() {
  const [state, dispatch] = useReducer(chatReducer, initialState);
  const [userId] = useState("demo_user");
  const [refreshTrigger, setRefreshTrigger] = useState(0);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [showAdmin, setShowAdmin] = useState(false);
  const [apiUp, setApiUp] = useState(false);
  const [ollamaUp, setOllamaUp] = useState(false);
  const [telegramOk, setTelegramOk] = useState(TELEGRAM_CONFIGURED);
  const [otelEnabled, setOtelEnabled] = useState(false);
  const [aspireUrl, setAspireUrl] = useState("http://localhost:18888");

  useEffect(() => {
    const check = async () => {
      try {
        const h = await getHealth();
        setApiUp(h.status === "ok");
        setOllamaUp(h.ollama_reachable);
        setTelegramOk(h.telegram_configured);
        setOtelEnabled(h.otel_enabled);
        setAspireUrl(h.otel_ui_url);
      } catch {
        setApiUp(false);
        setOllamaUp(false);
      }
    };
    void check();
    const interval = setInterval(check, 300_000);
    return () => clearInterval(interval);
  }, []);

  const services: ServiceRow[] = [
    { label: "Backend API", state: apiUp      ? "ok" : "down" },
    { label: "Ollama LLM",  state: ollamaUp   ? "ok" : "down" },
    { label: "Telegram",    state: telegramOk ? "ok" : "inactive" },
    { label: "Aspire",      detail: "OTEL",  state: otelEnabled ? "ok" : "inactive" },
  ];

  const handleConversationCreated = (id: number) => {
    setRefreshTrigger((n) => n + 1);
    dispatch({ type: "SET_CONVERSATION_ID", conversationId: id });
  };

  const saveTurnsCache = (id: number | null) => {
    if (!id) return;
    const done = state.history.filter((t) => !t.isStreaming);
    if (!done.length) return;
    try { sessionStorage.setItem(`turns_v1_${id}`, JSON.stringify(done)); } catch {}
  };

  const handleSelectConversation = (id: number) => {
    saveTurnsCache(state.conversationId);
    dispatch({ type: "RESET", conversationId: id });
  };

  const handleNew = () => {
    saveTurnsCache(state.conversationId);
    dispatch({ type: "RESET", conversationId: null });
  };

  return (
    <ChatContext.Provider value={{ state, dispatch }}>
      <div style={{ display: "flex", height: "100%", background: "var(--bg-page)" }}>

        {/* Sidebar */}
        {sidebarOpen && (
          <aside style={{
            width: 240, minWidth: 240,
            display: "flex", flexDirection: "column",
            background: "var(--sidebar-bg)",
            borderRight: "1px solid rgba(255,255,255,.05)",
          }}>
            {/* Brand */}
            <div style={{ padding: "20px 16px 16px", borderBottom: "1px solid rgba(255,255,255,.07)" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <div style={{
                  width: 36, height: 36,
                  background: "linear-gradient(135deg,#fb7185,#e11d48)",
                  borderRadius: 10,
                  display: "flex", alignItems: "center", justifyContent: "center",
                  fontSize: 18, boxShadow: "0 2px 10px rgba(244,63,94,.45)",
                }}>🛡️</div>
                <div>
                  <div style={{ color: "#fff", fontWeight: 700, fontSize: 14, letterSpacing: "-.01em" }}>ACME Insurances</div>
                  <div style={{ color: "var(--sidebar-text)", fontSize: 11, marginTop: 1 }}>AI Assistant · PoC</div>
                </div>
              </div>
            </div>

            {/* Conversations (grows to fill) */}
            <div style={{ flex: 1, overflow: "hidden", display: "flex", flexDirection: "column" }}>
              <ConversationList
                userId={userId}
                activeId={state.conversationId}
                refreshTrigger={refreshTrigger}
                onSelect={handleSelectConversation}
                onNew={handleNew}
              />
            </div>

            {/* Policy Upload */}
            <DocumentUpload />

            {/* Services status */}
            <div style={{
              padding: "10px 16px 8px",
              borderTop: "1px solid rgba(255,255,255,.07)",
            }}>
              <div style={{
                fontSize: 9, fontWeight: 700, letterSpacing: ".08em",
                textTransform: "uppercase",
                color: "rgba(161,161,170,.4)",
                marginBottom: 6,
              }}>Services</div>
              {services.map((svc) => (
                <ServiceStatusRow key={svc.label} {...svc} />
              ))}
            </div>

            {/* User footer */}
            <div style={{
              padding: "10px 16px 14px",
              borderTop: "1px solid rgba(255,255,255,.07)",
              display: "flex", alignItems: "center", gap: 8,
            }}>
              <div style={{
                width: 28, height: 28,
                background: "rgba(255,255,255,.08)",
                borderRadius: "50%",
                display: "flex", alignItems: "center", justifyContent: "center",
                fontSize: 13,
              }}>👤</div>
              <span style={{ color: "var(--sidebar-text)", fontSize: 12 }}>{userId}</span>
            </div>
          </aside>
        )}

        {/* Main */}
        <main style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column" }}>
          {/* Top bar */}
          <header style={{
            height: 52,
            background: "var(--bg-card)",
            borderBottom: "1px solid var(--border)",
            display: "flex", alignItems: "center", gap: 12,
            padding: "0 20px",
            boxShadow: "var(--shadow-sm)",
          }}>
            <button
              onClick={() => setSidebarOpen((v) => !v)}
              style={{
                background: "none", border: "none", cursor: "pointer",
                color: "var(--text-secondary)", fontSize: 18, padding: "4px 6px",
                borderRadius: 6, lineHeight: 1,
              }}
              title="Toggle sidebar"
            >☰</button>

            <div style={{ width: 1, height: 20, background: "var(--border)" }} />

            <span style={{ fontWeight: 600, fontSize: 14, color: "var(--text-primary)" }}>
              {state.conversationId
                ? `Conversation #${state.conversationId}`
                : "New conversation"}
            </span>

            {/* Right side */}
            <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 10 }}>
              {/* Telemetry link */}
              <a
                href={aspireUrl}
                target="_blank"
                rel="noreferrer"
                title="Open Aspire telemetry dashboard"
                style={{
                  display: "flex", alignItems: "center", gap: 5,
                  background: otelEnabled ? "#fff1f2" : "#f4f4f5",
                  border: `1px solid ${otelEnabled ? "#fecdd3" : "#e4e4e7"}`,
                  borderRadius: 8,
                  padding: "4px 10px",
                  textDecoration: "none",
                  color: otelEnabled ? "var(--brand-dark)" : "var(--text-muted)",
                  fontSize: 11, fontWeight: 600,
                  transition: "background .15s",
                  letterSpacing: ".01em",
                }}
                onMouseEnter={(e) => { (e.currentTarget as HTMLAnchorElement).style.background = otelEnabled ? "#ffe4e6" : "#e4e4e7"; }}
                onMouseLeave={(e) => { (e.currentTarget as HTMLAnchorElement).style.background = otelEnabled ? "#fff1f2" : "#f4f4f5"; }}
              >
                <span>📊</span>
                <span>Telemetry</span>
                {otelEnabled && (
                  <span style={{
                    width: 5, height: 5, borderRadius: "50%",
                    background: "#22c55e", boxShadow: "0 0 4px #22c55e",
                  }} />
                )}
              </a>

              <button
                onClick={() => setShowAdmin((v) => !v)}
                style={{
                  display: "flex", alignItems: "center", gap: 5,
                  background: showAdmin ? "rgba(0,48,135,.1)" : "#f4f4f5",
                  border: `1px solid ${showAdmin ? "rgba(0,48,135,.25)" : "#e4e4e7"}`,
                  borderRadius: 8,
                  padding: "4px 10px",
                  cursor: "pointer",
                  color: showAdmin ? "var(--brand-dark)" : "var(--text-muted)",
                  fontSize: 11, fontWeight: 600,
                }}
                title="Admin panel"
              >
                🗄️ Admin
              </button>

            </div>
          </header>

          {/* ChatPage stays mounted while Admin is open so in-flight streams
              complete and history is preserved. CSS hides it instead of unmounting. */}
          <div style={{ flex: 1, minHeight: 0, display: showAdmin ? "none" : "flex", flexDirection: "column" }}>
            <ChatPage
              conversationId={state.conversationId}
              userId={userId}
              telegramConfigured={TELEGRAM_CONFIGURED}
              onConversationCreated={handleConversationCreated}
            />
          </div>
          {showAdmin && <AdminPage />}
        </main>
      </div>
    </ChatContext.Provider>
  );
}
