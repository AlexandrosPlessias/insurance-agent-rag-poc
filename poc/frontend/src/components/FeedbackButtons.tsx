import { useState } from "react";
import { submitFeedback } from "../api/client";

interface Props {
  planId: string | null;
  conversationId: number | null;
  userId: string;
  turnKey: string;
  onRated: (key: string) => void;
  alreadyRated: boolean;
}

export function FeedbackButtons({
  planId,
  conversationId,
  userId,
  turnKey,
  onRated,
  alreadyRated,
}: Props) {
  const [submitting, setSubmitting] = useState(false);
  const [rated, setRated] = useState<1 | -1 | null>(null);

  if (!planId) return null;

  if (alreadyRated || rated !== null) {
    return (
      <div style={{
        display: "inline-flex", alignItems: "center", gap: 6,
        marginTop: 10,
        background: "#f0fdf4", border: "1px solid #bbf7d0",
        borderRadius: 20, padding: "4px 12px",
        fontSize: 12, color: "#15803d", fontWeight: 500,
      }}>
        {rated === 1 ? "👍" : rated === -1 ? "👎" : "✓"} Thanks for your feedback!
      </div>
    );
  }

  const rate = async (score: -1 | 1) => {
    setSubmitting(true);
    try {
      await submitFeedback(planId, score, userId, planId, conversationId);
      setRated(score);
      onRated(turnKey);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 10 }}>
      <span style={{ fontSize: 11, color: "var(--text-muted)" }}>Was this helpful?</span>
      <button
        onClick={() => rate(1)}
        disabled={submitting}
        title="Helpful"
        style={{
          background: "none", border: "1px solid var(--border)",
          borderRadius: 8, padding: "4px 10px", cursor: "pointer",
          fontSize: 14, transition: "all .15s",
        }}
        onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.background = "#f0fdf4"; (e.currentTarget as HTMLButtonElement).style.borderColor = "#16a34a"; }}
        onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.background = "none"; (e.currentTarget as HTMLButtonElement).style.borderColor = "var(--border)"; }}
      >👍</button>
      <button
        onClick={() => rate(-1)}
        disabled={submitting}
        title="Not helpful"
        style={{
          background: "none", border: "1px solid var(--border)",
          borderRadius: 8, padding: "4px 10px", cursor: "pointer",
          fontSize: 14, transition: "all .15s",
        }}
        onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.background = "#fef2f2"; (e.currentTarget as HTMLButtonElement).style.borderColor = "#dc2626"; }}
        onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.background = "none"; (e.currentTarget as HTMLButtonElement).style.borderColor = "var(--border)"; }}
      >👎</button>
    </div>
  );
}
