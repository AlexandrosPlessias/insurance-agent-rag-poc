import * as Collapsible from "@radix-ui/react-collapsible";
import { useRef, useState } from "react";
import { uploadDocument } from "../api/client";
import type { IngestResponse } from "../api/types";

export function DocumentUpload() {
  const [open, setOpen] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [year, setYear] = useState("");
  const [keywords, setKeywords] = useState("");
  const [category, setCategory] = useState("");
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState<IngestResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const reset = () => {
    setFile(null); setTitle(""); setYear(""); setKeywords(""); setCategory("");
    setResult(null); setError(null);
    if (inputRef.current) inputRef.current.value = "";
  };

  const handleIngest = async () => {
    if (!file) return;
    setUploading(true); setError(null); setResult(null);
    try {
      const res = await uploadDocument(
        file,
        title || undefined,
        year ? parseInt(year, 10) : undefined,
        keywords || undefined,
        category || undefined,
      );
      setResult(res);
      setFile(null);
      if (inputRef.current) inputRef.current.value = "";
    } catch (e) {
      setError(String(e).replace(/^Error:\s*/, ""));
    } finally {
      setUploading(false);
    }
  };

  const inputStyle: React.CSSProperties = {
    width: "100%",
    background: "rgba(255,255,255,.07)",
    border: "1px solid rgba(255,255,255,.12)",
    borderRadius: 7,
    padding: "6px 10px",
    fontSize: 12,
    color: "#e4e4e7",
    outline: "none",
    fontFamily: "inherit",
  };

  return (
    <div style={{ padding: "8px 12px", borderTop: "1px solid rgba(255,255,255,.07)" }}>
      <Collapsible.Root open={open} onOpenChange={setOpen}>
        <Collapsible.Trigger style={{
          background: "none", border: "none", cursor: "pointer",
          display: "flex", alignItems: "center", gap: 7, width: "100%",
          color: "var(--sidebar-text)", fontSize: 12, fontWeight: 500,
          padding: "6px 4px",
        }}>
          <span style={{ fontSize: 14 }}>📄</span>
          <span style={{ flex: 1, textAlign: "left" }}>Policy Upload</span>
          <span style={{ fontSize: 9, opacity: .7 }}>{open ? "▾" : "▸"}</span>
        </Collapsible.Trigger>

        <Collapsible.Content>
          <div style={{ paddingTop: 8, display: "flex", flexDirection: "column", gap: 7 }}>

            {result && (
              <div style={{
                background: "rgba(34,197,94,.12)", border: "1px solid rgba(34,197,94,.25)",
                borderRadius: 8, padding: "8px 10px", fontSize: 11, color: "#86efac",
                lineHeight: 1.5,
              }}>
                ✓ Indexed <strong>{result.chunks_indexed}</strong> chunks from{" "}
                <strong>{result.source}</strong> ({result.page_count} pages)
                <button
                  onClick={reset}
                  style={{
                    display: "block", marginTop: 4,
                    background: "none", border: "none", cursor: "pointer",
                    color: "rgba(134,239,172,.7)", fontSize: 10, padding: 0,
                  }}
                >Upload another →</button>
              </div>
            )}

            {error && (
              <div style={{
                background: "rgba(244,63,94,.12)", border: "1px solid rgba(244,63,94,.25)",
                borderRadius: 8, padding: "8px 10px", fontSize: 11, color: "#fda4af",
              }}>⚠ {error}</div>
            )}

            {!result && (
              <>
                {/* File picker */}
                <div
                  onClick={() => inputRef.current?.click()}
                  style={{
                    border: "1.5px dashed rgba(255,255,255,.18)",
                    borderRadius: 8, padding: "10px 8px",
                    textAlign: "center", cursor: "pointer",
                    color: file ? "#e4e4e7" : "var(--sidebar-text)",
                    fontSize: 11, lineHeight: 1.5,
                    background: file ? "rgba(255,255,255,.06)" : "transparent",
                    transition: "background .15s",
                  }}
                  onMouseEnter={(e) => { if (!file) (e.currentTarget as HTMLDivElement).style.background = "rgba(255,255,255,.04)"; }}
                  onMouseLeave={(e) => { if (!file) (e.currentTarget as HTMLDivElement).style.background = "transparent"; }}
                >
                  {file ? (
                    <><span style={{ fontSize: 14 }}>📄</span> {file.name}</>
                  ) : (
                    <><span style={{ fontSize: 14 }}>📁</span><br />Click to select PDF</>
                  )}
                </div>
                <input
                  ref={inputRef}
                  type="file"
                  accept=".pdf,application/pdf"
                  style={{ display: "none" }}
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) { setFile(f); setResult(null); setError(null); }
                  }}
                />

                <input
                  style={inputStyle} placeholder="Title (optional)"
                  value={title} onChange={(e) => setTitle(e.target.value)}
                />
                <input
                  style={inputStyle} placeholder="Year (optional)" type="number"
                  value={year} onChange={(e) => setYear(e.target.value)}
                />
                <input
                  style={inputStyle} placeholder="Keywords, comma-separated"
                  value={keywords} onChange={(e) => setKeywords(e.target.value)}
                />
                <input
                  style={inputStyle} placeholder="Category (optional)"
                  value={category} onChange={(e) => setCategory(e.target.value)}
                />

                <button
                  onClick={handleIngest}
                  disabled={!file || uploading}
                  style={{
                    background: file && !uploading
                      ? "linear-gradient(135deg,#fb7185,#e11d48)"
                      : "rgba(255,255,255,.07)",
                    border: "none", borderRadius: 8,
                    color: file && !uploading ? "#fff" : "rgba(161,161,170,.5)",
                    fontWeight: 600, fontSize: 12,
                    padding: "8px 0", cursor: file && !uploading ? "pointer" : "not-allowed",
                    width: "100%",
                    boxShadow: file && !uploading ? "0 2px 8px rgba(244,63,94,.3)" : "none",
                    transition: "all .2s",
                  }}
                >
                  {uploading ? "Indexing…" : "📥 Ingest"}
                </button>
              </>
            )}
          </div>
        </Collapsible.Content>
      </Collapsible.Root>
    </div>
  );
}
