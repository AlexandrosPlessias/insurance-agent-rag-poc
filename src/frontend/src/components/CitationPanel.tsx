import * as Collapsible from "@radix-ui/react-collapsible";
import * as Popover from "@radix-ui/react-popover";
import { useState } from "react";
import { sourceUrl } from "../api/client";
import type { Citation } from "../api/types";

interface Props {
  citations: Citation[];
}

export function CitationPanel({ citations }: Props) {
  const [open, setOpen] = useState(false);

  if (!citations || citations.length === 0) return null;

  const bySource = citations.reduce<Record<string, Citation[]>>((acc, c) => {
    (acc[c.source] ??= []).push(c);
    return acc;
  }, {});

  const sourceCount = Object.keys(bySource).length;

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
          <span>📎</span>
          {sourceCount} source{sourceCount > 1 ? "s" : ""} · {citations.length} chunk{citations.length > 1 ? "s" : ""}
        </Collapsible.Trigger>

        <Collapsible.Content>
          <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 8 }}>
            {Object.entries(bySource).map(([source, chunks]) => (
              <div key={source} style={{
                border: "1px solid var(--border)",
                borderRadius: 10,
                overflow: "hidden",
                background: "var(--bg-card)",
                boxShadow: "var(--shadow-sm)",
              }}>
                {/* Header */}
                <div style={{
                  display: "flex", alignItems: "center", justifyContent: "space-between",
                  padding: "9px 14px",
                  background: "#fafbff",
                  borderBottom: chunks.length > 0 ? "1px solid var(--border)" : "none",
                }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ fontSize: 15 }}>📄</span>
                    <span style={{ fontWeight: 600, fontSize: 12, color: "var(--text-primary)" }}>
                      {source}
                    </span>
                    <span style={{
                      background: "var(--brand-light)", color: "var(--brand)",
                      fontSize: 10, fontWeight: 700,
                      padding: "1px 7px", borderRadius: 20,
                    }}>
                      {chunks.length} chunk{chunks.length > 1 ? "s" : ""}
                    </span>
                  </div>
                  <a
                    href={sourceUrl(source)}
                    target="_blank"
                    rel="noreferrer"
                    style={{
                      fontSize: 11, fontWeight: 600,
                      color: "var(--brand)", textDecoration: "none",
                      padding: "4px 10px",
                      background: "var(--brand-light)",
                      borderRadius: 6,
                    }}
                  >
                    ↓ PDF
                  </a>
                </div>

                {/* Chunks */}
                <div style={{ display: "flex", flexWrap: "wrap", gap: 6, padding: "10px 14px" }}>
                  {chunks.map((c, i) => (
                    <Popover.Root key={i}>
                      <Popover.Trigger style={{
                        background: "var(--brand-light)",
                        border: "1px solid #c7d9f0",
                        borderRadius: 6, padding: "4px 10px",
                        fontSize: 11, fontWeight: 500,
                        color: "var(--brand)", cursor: "pointer",
                        display: "flex", alignItems: "center", gap: 5,
                      }}>
                        <span style={{ fontWeight: 700 }}>[{c.chunk_index ?? i + 1}]</span>
                        <span style={{ color: "var(--text-secondary)", maxWidth: 140, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                          {c.section_title || c.section || "Chunk"}
                        </span>
                      </Popover.Trigger>
                      <Popover.Portal>
                        <Popover.Content
                          style={{
                            zIndex: 50, width: 340, maxHeight: 280, overflowY: "auto",
                            background: "#fff",
                            border: "1px solid var(--border)",
                            borderRadius: 12,
                            boxShadow: "var(--shadow-lg)",
                            padding: "14px 16px",
                            fontSize: 12, lineHeight: 1.6,
                            color: "var(--text-secondary)",
                          }}
                          sideOffset={6}
                        >
                          <p style={{ fontWeight: 600, fontSize: 11, color: "var(--brand)", marginBottom: 8 }}>
                            {c.section_title || c.section || `Chunk ${c.chunk_index ?? i + 1}`}
                          </p>
                          <p style={{ whiteSpace: "pre-wrap" }}>{c.content}</p>
                          <Popover.Arrow style={{ fill: "#fff" }} />
                        </Popover.Content>
                      </Popover.Portal>
                    </Popover.Root>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </Collapsible.Content>
      </Collapsible.Root>
    </div>
  );
}
