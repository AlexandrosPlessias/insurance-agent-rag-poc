import { reportUrl } from "../api/client";

interface Props {
  reportYear: number | null;
  reportKind: string | null;
}

const FORMATS = [
  { ext: "docx" as const, label: "Word Document", icon: "📝", color: "#2563eb" },
  { ext: "pdf"  as const, label: "PDF",           icon: "📕", color: "#dc2626" },
  { ext: "md"   as const, label: "Markdown",      icon: "📄", color: "#52525b" },
];

export function ReportDownloads({ reportYear, reportKind }: Props) {
  if (reportKind !== "executive" || !reportYear) return null;

  return (
    <div style={{ marginTop: 14 }}>
      <div style={{
        fontSize: 10, fontWeight: 700, letterSpacing: ".07em",
        textTransform: "uppercase", color: "var(--text-muted)",
        marginBottom: 8,
      }}>
        📥 Download {reportYear} Annual Report
      </div>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        {FORMATS.map(({ ext, label, icon, color }) => (
          <a
            key={ext}
            href={reportUrl(reportYear, ext)}
            download
            style={{
              display: "flex", alignItems: "center", gap: 6,
              padding: "7px 14px",
              border: `1px solid ${color}33`,
              borderRadius: 9,
              background: `${color}0a`,
              color,
              fontSize: 12, fontWeight: 600,
              textDecoration: "none",
              transition: "background .15s, border-color .15s",
            }}
            onMouseEnter={(e) => {
              const el = e.currentTarget as HTMLAnchorElement;
              el.style.background = `${color}18`;
              el.style.borderColor = `${color}66`;
            }}
            onMouseLeave={(e) => {
              const el = e.currentTarget as HTMLAnchorElement;
              el.style.background = `${color}0a`;
              el.style.borderColor = `${color}33`;
            }}
          >
            <span>{icon}</span>
            <span>{label}</span>
          </a>
        ))}
      </div>
    </div>
  );
}
