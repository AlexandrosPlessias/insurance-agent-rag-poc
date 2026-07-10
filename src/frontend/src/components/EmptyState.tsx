interface Props {
  onPrompt: (text: string) => void;
}

const QUICK_STARTS = [
  {
    icon: "📄",
    label: "Policy coverage",
    sub: "Refund window lookup",
    prompt: "What is the refund window in the 2024 customer guidelines?",
    color: "#fff1f2",
    accent: "#f43f5e",
  },
  {
    icon: "📊",
    label: "KPI report",
    sub: "2024 financial figures",
    prompt: "What were the total claims paid in 2024?",
    color: "#f0fdf4",
    accent: "#059669",
  },
  {
    icon: "📝",
    label: "Executive summary",
    sub: "Annual report generation",
    prompt: "Generate the executive annual report for 2024",
    color: "#f5f3ff",
    accent: "#7c3aed",
  },
];

export function EmptyState({ onPrompt }: Props) {
  return (
    <div style={{
      display: "flex", flexDirection: "column",
      alignItems: "center", justifyContent: "center",
      height: "100%", padding: "40px 24px",
      textAlign: "center",
    }}>
      {/* Logo mark */}
      <div style={{
        width: 72, height: 72,
        background: "linear-gradient(135deg,#fb7185,#e11d48)",
        borderRadius: 20,
        display: "flex", alignItems: "center", justifyContent: "center",
        fontSize: 36,
        boxShadow: "0 8px 28px rgba(244,63,94,.35)",
        marginBottom: 24,
      }}>🛡️</div>

      <h1 style={{
        fontSize: 26, fontWeight: 700,
        color: "var(--text-primary)",
        letterSpacing: "-.02em",
        marginBottom: 8,
      }}>
        ACME Insurances Assistant
      </h1>
      <p style={{ fontSize: 15, color: "var(--text-muted)", marginBottom: 36 }}>
        What can I help you with today?
      </p>

      <div style={{ display: "flex", gap: 14, flexWrap: "wrap", justifyContent: "center", maxWidth: 640 }}>
        {QUICK_STARTS.map((qs) => (
          <button
            key={qs.label}
            onClick={() => onPrompt(qs.prompt)}
            style={{
              background: "var(--bg-card)",
              border: "1.5px solid var(--border)",
              borderRadius: 14,
              padding: "16px 20px",
              textAlign: "left",
              cursor: "pointer",
              minWidth: 180, maxWidth: 200,
              boxShadow: "var(--shadow-sm)",
              transition: "all .2s",
            }}
            onMouseEnter={(e) => {
              const el = e.currentTarget as HTMLButtonElement;
              el.style.borderColor = qs.accent;
              el.style.boxShadow = `0 4px 16px ${qs.accent}22, var(--shadow-md)`;
              el.style.transform = "translateY(-2px)";
            }}
            onMouseLeave={(e) => {
              const el = e.currentTarget as HTMLButtonElement;
              el.style.borderColor = "var(--border)";
              el.style.boxShadow = "var(--shadow-sm)";
              el.style.transform = "translateY(0)";
            }}
          >
            <div style={{
              width: 38, height: 38,
              background: qs.color,
              borderRadius: 10,
              display: "flex", alignItems: "center", justifyContent: "center",
              fontSize: 20, marginBottom: 10,
              border: `1px solid ${qs.accent}22`,
            }}>
              {qs.icon}
            </div>
            <div style={{ fontWeight: 600, fontSize: 13, color: "var(--text-primary)", marginBottom: 3 }}>
              {qs.label}
            </div>
            <div style={{ fontSize: 11, color: "var(--text-muted)" }}>{qs.sub}</div>
          </button>
        ))}
      </div>
    </div>
  );
}
