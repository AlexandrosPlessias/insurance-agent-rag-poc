import * as Collapsible from "@radix-ui/react-collapsible";
import { useState } from "react";

interface DataOp {
  metric: string;
  filters: Record<string, unknown>;
  group_by: string[];
  aggregation: string;
  compare_to: unknown | null;
  sort_by: string | null;
  limit: number | null;
  _drilldown: boolean;
  _inherited: string[];
  _changed: string[];
}

interface Props {
  dataOperation: unknown;
  route: string;
}

const chipBase: React.CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  borderRadius: 4,
  padding: "2px 8px",
  fontSize: 11,
  fontWeight: 600,
  marginRight: 4,
};

const inheritedChip: React.CSSProperties = {
  ...chipBase,
  background: "#172554",
  color: "#93c5fd",
  border: "1px solid #1e40af",
};

const changedChip: React.CSSProperties = {
  ...chipBase,
  background: "#431407",
  color: "#fdba74",
  border: "1px solid #9a3412",
};

function formatFilters(filters: Record<string, unknown>): string {
  const parts = Object.entries(filters)
    .filter(([, v]) => v !== null && v !== undefined && (!Array.isArray(v) || v.length > 0))
    .map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(", ") : String(v)}`);
  return parts.length ? parts.join(" · ") : "—";
}

function OpRow({ label, value }: { label: string; value: string }) {
  if (!value || value === "—") return null;
  return (
    <div style={{ display: "flex", gap: 8, fontSize: 12, marginBottom: 2 }}>
      <span style={{ color: "var(--text-muted, #9ca3af)", minWidth: 90, flexShrink: 0 }}>{label}</span>
      <span style={{ color: "var(--text, #e5e7eb)", wordBreak: "break-all" }}>{value}</span>
    </div>
  );
}

export function OperationExpander({ dataOperation, route }: Props) {
  const [open, setOpen] = useState(false);
  const [rawOpen, setRawOpen] = useState(false);

  if (route !== "data" || !dataOperation) return null;

  const op = dataOperation as DataOp;
  const isDrilldown = op._drilldown && (op._inherited?.length > 0 || op._changed?.length > 0);

  return (
    <Collapsible.Root open={open} onOpenChange={setOpen} className="mt-2">
      <Collapsible.Trigger className="flex items-center gap-1 text-xs text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200">
        <span>{open ? "▾" : "▸"}</span>
        <span>How this was computed</span>
      </Collapsible.Trigger>
      <Collapsible.Content>
        <div style={{ marginTop: 8, padding: "10px 14px", borderRadius: 8, background: "var(--surface-2, #111827)", border: "1px solid var(--border, #1f2937)" }}>

          {/* Drill-down provenance chips */}
          {isDrilldown && (
            <div style={{ marginBottom: 10, display: "flex", flexWrap: "wrap", gap: 4, alignItems: "center" }}>
              {op._inherited.length > 0 && (
                <span style={{ fontSize: 11, color: "var(--text-muted, #9ca3af)", marginRight: 4 }}>♻ Inherited</span>
              )}
              {op._inherited.map((f) => (
                <span key={f} style={inheritedChip}>{f}</span>
              ))}
              {op._changed.length > 0 && (
                <>
                  <span style={{ fontSize: 11, color: "var(--text-muted, #9ca3af)", marginLeft: 8, marginRight: 4 }}>✎ Changed</span>
                  {op._changed.map((f) => (
                    <span key={f} style={changedChip}>{f}</span>
                  ))}
                </>
              )}
            </div>
          )}

          {/* Structured fields */}
          <OpRow label="metric" value={op.metric ?? "—"} />
          <OpRow label="group_by" value={op.group_by?.join(", ") ?? "—"} />
          <OpRow label="aggregation" value={op.aggregation ?? "—"} />
          <OpRow label="filters" value={formatFilters(op.filters ?? {})} />
          {op.sort_by && <OpRow label="sort_by" value={op.sort_by} />}
          {op.limit != null && <OpRow label="limit" value={String(op.limit)} />}

          {/* Raw JSON toggle */}
          <Collapsible.Root open={rawOpen} onOpenChange={setRawOpen} style={{ marginTop: 8 }}>
            <Collapsible.Trigger style={{ fontSize: 11, color: "var(--text-muted, #9ca3af)", cursor: "pointer", background: "none", border: "none", padding: 0 }}>
              {rawOpen ? "▾" : "▸"} Raw JSON
            </Collapsible.Trigger>
            <Collapsible.Content>
              <pre style={{ marginTop: 6, overflowX: "auto", borderRadius: 6, background: "#0d1117", padding: 10, fontSize: 11, color: "#d1d5db" }}>
                {JSON.stringify(dataOperation, null, 2)}
              </pre>
            </Collapsible.Content>
          </Collapsible.Root>
        </div>
      </Collapsible.Content>
    </Collapsible.Root>
  );
}
