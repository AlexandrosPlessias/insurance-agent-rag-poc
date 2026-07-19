import * as Collapsible from "@radix-ui/react-collapsible";
import { useState, useEffect } from "react";
import type { StageStatus } from "../store/chatStore";

interface Props {
  stages: Record<string, StageStatus>;
  skillLabels: Record<string, string>;
  route: string;
  isStreaming: boolean;
  reformulatedQuery?: string | null;
}

const SKILL_LABELS: Record<string, string> = {
  "answer-policy-question": "Policy Q&A",
  "compute-kpi": "KPI Query",
  "executive-section-summary": "Exec Report",
  "clarify-year": "Clarify Year",
  "out-of-year-fallback": "Year Guard",
  "decline": "Out of Scope",
};

const SUBSTAGE_TOOL: Record<string, string> = {
  // answer-policy-question sub-stages
  reformulate: "LLM",
  retrieve: "Chroma",
  answer: "LLM",
  validate: "Validator",
  // executive-section-summary tools_used
  kpi_query: "KPI DB",
  vector_search: "Chroma",
  knowledge_base_lookup: "KB",
  // compute-kpi tools_used
  clarifier_check: "LLM",
};

function StatusDot({ status }: { status: StageStatus }) {
  const cfg = {
    done:     { bg: "#dcfce7", border: "#16a34a", dot: "#16a34a", icon: "✓" },
    running:  { bg: "#fff1f2", border: "#f43f5e", dot: "#f43f5e", icon: "⟳" },
    off_path: { bg: "#f4f4f5", border: "#d4d4d8", dot: "#a1a1aa", icon: "—" },
    pending:  { bg: "#f4f4f5", border: "#e4e4e7", dot: "#d4d4d8", icon: "·" },
  }[status] ?? { bg: "#f4f4f5", border: "#e4e4e7", dot: "#d4d4d8", icon: "·" };

  return (
    <div style={{
      width: 22, height: 22, borderRadius: "50%",
      background: cfg.bg, border: `2px solid ${cfg.border}`,
      display: "flex", alignItems: "center", justifyContent: "center",
      fontSize: 11, fontWeight: 700, color: cfg.dot,
      animation: status === "running" ? "spin 1.2s linear infinite" : "none",
    }}>
      {cfg.icon}
    </div>
  );
}

function NodeChip({ label, status }: { label: string; status: StageStatus }) {
  const textColor = {
    done: "#15803d", running: "#e11d48", off_path: "#a1a1aa", pending: "#71717a",
  }[status] ?? "#71717a";

  return (
    <div style={{
      display: "flex", flexDirection: "column", alignItems: "center", gap: 4,
      minWidth: 72,
    }}>
      <StatusDot status={status} />
      <span style={{ fontSize: 11, fontWeight: 500, color: textColor, textAlign: "center", lineHeight: 1.2 }}>
        {label}
      </span>
    </div>
  );
}

const Connector = () => (
  <div style={{ width: 24, height: 2, background: "#e4e4e7", marginTop: -10, flexShrink: 0 }} />
);

export function PipelineStepper({ stages, skillLabels, route, isStreaming, reformulatedQuery }: Props) {
  const isAgentic = route === "agentic";
  const [open, setOpen] = useState(isAgentic);

  useEffect(() => {
    if (isAgentic) setOpen(true);
  }, [isAgentic]);

  const getStatus = (key: string): StageStatus => stages[key] ?? "pending";

  const workerKeys = Object.keys(stages)
    .filter((k) => /^worker\.[^.]+$/.test(k))
    .sort();

  const allNodes = ["planner", "orchestrator", ...workerKeys, "assembler"];

  const workerLabel = (key: string): string => {
    const skillId = skillLabels[key];
    if (skillId) return `${SKILL_LABELS[skillId] ?? skillId} (skill)`;
    return key.replace(/^worker\./, "Worker ");
  };

  const nodeLabel = (key: string) => {
    if (key.startsWith("worker.")) return workerLabel(key);
    return key.charAt(0).toUpperCase() + key.slice(1);
  };

  const allNodeSet = new Set(allNodes);

  // Only show sub-stages that are direct children of a known worker node
  // (e.g. worker.step-1.kpi_query is valid; bare "answer" or rag.reformulate are not).
  const subStageKeys = Object.keys(stages).filter((k) => {
    if (!stages[k]) return false;
    const dot = k.lastIndexOf(".");
    if (dot < 0) return false;
    return allNodeSet.has(k.slice(0, dot));
  });

  const hasActivity = Object.keys(stages).length > 0;
  if (!hasActivity) return null;

  const hasRunning = Object.values(stages).some((s) => s === "running");
  const isRunning = isStreaming && hasRunning;
  const isDone = !isRunning && Object.values(stages).some((s) => s === "done");

  return (
    <div style={{ marginTop: 10 }}>
      <Collapsible.Root open={open} onOpenChange={setOpen}>
        <Collapsible.Trigger style={{
          background: "none", border: "none", cursor: "pointer",
          display: "flex", alignItems: "center", gap: 6,
          color: "var(--text-muted)", fontSize: 12, fontWeight: 500,
          padding: "2px 0",
        }}>
          <span style={{ fontSize: 10 }}>{open ? "▾" : "▸"}</span>
          Pipeline
          {isRunning && (
            <span style={{
              background: "#fff1f2", color: "#e11d48",
              fontSize: 10, fontWeight: 700,
              padding: "1px 7px", borderRadius: 20,
              border: "1px solid #fecdd3",
            }}>Running</span>
          )}
          {isDone && (
            <span style={{
              background: "#f0fdf4", color: "#16a34a",
              fontSize: 10, fontWeight: 700,
              padding: "1px 7px", borderRadius: 20,
              border: "1px solid #bbf7d0",
            }}>Done</span>
          )}
        </Collapsible.Trigger>

        <Collapsible.Content>
          {/* Node flow */}
          <div style={{
            display: "flex", alignItems: "center", flexWrap: "wrap", gap: 0,
            marginTop: 10,
            background: "#fafafa",
            border: "1px solid var(--border)",
            borderRadius: 10,
            padding: "12px 16px",
          }}>
            {allNodes.map((key, i) => (
              <div key={key} style={{ display: "flex", alignItems: "center" }}>
                <NodeChip
                  label={nodeLabel(key)}
                  status={getStatus(key)}
                />
                {i < allNodes.length - 1 && <Connector />}
              </div>
            ))}
          </div>

          {/* Sub-stage pills — one row per worker */}
          {workerKeys.map((wk) => {
            const wkSubs = subStageKeys.filter((k) => k.startsWith(`${wk}.`));
            if (!wkSubs.length) return null;
            return (
              <div key={wk} style={{ display: "flex", flexWrap: "wrap", gap: 5, marginTop: 6 }}>
                {wkSubs.map((k) => {
                  const s = stages[k];
                  const stepName = k.split(".").pop() ?? k;
                  const toolHint = SUBSTAGE_TOOL[stepName];
                  return (
                    <span key={k} style={{
                      fontSize: 10, fontWeight: 500,
                      padding: "2px 8px", borderRadius: 20,
                      background: s === "done" ? "#f0fdf4" : s === "running" ? "#fff1f2" : "#f4f4f5",
                      color: s === "done" ? "#15803d" : s === "running" ? "#e11d48" : "#71717a",
                      border: `1px solid ${s === "done" ? "#bbf7d0" : s === "running" ? "#fecdd3" : "#e4e4e7"}`,
                    }}>
                      {stepName}{toolHint ? <span style={{ opacity: .55 }}> · {toolHint}</span> : null}
                    </span>
                  );
                })}
              </div>
            );
          })}
        </Collapsible.Content>
      </Collapsible.Root>
      {reformulatedQuery && (
        <div style={{
          marginTop: 5, fontSize: 11,
          display: "flex", gap: 4, alignItems: "baseline",
          color: "var(--text-primary)",
        }}>
          <span style={{ fontWeight: 600, flexShrink: 0, color: "var(--text-muted)" }}>Reformulated:</span>
          <span style={{ fontStyle: "italic" }}>{reformulatedQuery}</span>
        </div>
      )}
      <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
    </div>
  );
}
