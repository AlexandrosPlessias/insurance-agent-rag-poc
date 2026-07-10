import { useEffect, useState } from "react";
import { deleteConversation, listConversations } from "../api/client";
import type { Conversation } from "../api/types";

interface Props {
  userId: string;
  activeId: number | null;
  refreshTrigger: number;
  onSelect: (id: number) => void;
  onNew: () => void;
}

export function ConversationList({ userId, activeId, refreshTrigger, onSelect, onNew }: Props) {
  const [convs, setConvs] = useState<Conversation[]>([]);

  useEffect(() => {
    listConversations(userId).then(setConvs).catch(() => setConvs([]));
  }, [userId, refreshTrigger]);

  const handleDelete = async (e: React.MouseEvent, id: number) => {
    e.stopPropagation();
    await deleteConversation(id);
    sessionStorage.removeItem(`turns_v1_${id}`);
    setConvs((prev) => prev.filter((c) => c.id !== id));
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      {/* New conversation button */}
      <div style={{ padding: "14px 12px 10px" }}>
        <button
          onClick={onNew}
          style={{
            width: "100%",
            background: "linear-gradient(135deg,#fb7185,#e11d48)",
            border: "none", borderRadius: 10,
            color: "#fff", fontWeight: 600, fontSize: 13,
            padding: "10px 0", cursor: "pointer",
            boxShadow: "0 2px 10px rgba(244,63,94,.35)",
            letterSpacing: ".01em",
            display: "flex", alignItems: "center", justifyContent: "center", gap: 6,
          }}
        >
          <span style={{ fontSize: 16, lineHeight: 1 }}>＋</span> New conversation
        </button>
      </div>

      {/* Section label */}
      <div style={{
        padding: "4px 16px 6px",
        color: "rgba(161,161,170,.45)",
        fontSize: 10, fontWeight: 700,
        textTransform: "uppercase", letterSpacing: ".08em",
      }}>
        Recent
      </div>

      {/* List */}
      <div style={{ flex: 1, overflowY: "auto" }}>
        {convs.length === 0 ? (
          <div style={{ padding: "12px 16px", color: "rgba(161,161,170,.5)", fontSize: 12 }}>
            No conversations yet
          </div>
        ) : (
          convs.map((c) => {
            const isActive = c.id === activeId;
            return (
              <div
                key={c.id}
                onClick={() => onSelect(c.id)}
                className="conv-item"
                style={{
                  display: "flex", alignItems: "center",
                  padding: "9px 12px 9px 14px",
                  cursor: "pointer",
                  borderRadius: 8,
                  margin: "1px 6px",
                  background: isActive
                    ? "linear-gradient(90deg,rgba(244,63,94,.2),rgba(225,29,72,.1))"
                    : "transparent",
                  borderLeft: isActive ? "3px solid #f43f5e" : "3px solid transparent",
                  transition: "background .15s",
                  position: "relative",
                }}
                onMouseEnter={(e) => {
                  if (!isActive) (e.currentTarget as HTMLDivElement).style.background = "rgba(255,255,255,.05)";
                }}
                onMouseLeave={(e) => {
                  if (!isActive) (e.currentTarget as HTMLDivElement).style.background = "transparent";
                }}
              >
                <span style={{
                  flex: 1,
                  overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                  fontSize: 13,
                  color: isActive ? "#fff" : "var(--sidebar-text)",
                  fontWeight: isActive ? 600 : 400,
                }}>
                  {c.title ?? `Conversation ${c.id}`}
                </span>
                <button
                  onClick={(e) => handleDelete(e, c.id)}
                  className="conv-delete"
                  style={{
                    background: "none", border: "none", cursor: "pointer",
                    color: "rgba(161,161,170,.45)", fontSize: 13, padding: "2px 4px",
                    borderRadius: 4, opacity: 0, transition: "opacity .15s",
                    flexShrink: 0,
                  }}
                  title="Delete"
                >✕</button>
              </div>
            );
          })
        )}
      </div>

      <style>{`
        .conv-item:hover .conv-delete { opacity: 1 !important; }
        .conv-delete:hover { color: #f43f5e !important; }
      `}</style>
    </div>
  );
}
