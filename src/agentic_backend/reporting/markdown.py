"""Markdown report formatting for policy summaries."""
from datetime import datetime

from agentic_backend.rag.retriever import RetrievedChunk


def _row(values: list[str]) -> str:
    return "| " + " | ".join(values) + " |"


def build_policy_report(
    data: dict,
    chunks: list[RetrievedChunk],
    chart_b64: str = "",
    user_activity_bullets: list[str] | None = None,
) -> str:
    """Render a Markdown policy summary.

    Sections:
      - Header (title + timestamp)
      - User Activity (if provided)
      - Policy Details, Coverage, Premium (+ chart), Claims, Exclusions
      - Sources
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    sections: list[str] = [
        "# Policy Summary Report",
        f"*Generated: {now}*",
        "",
    ]

    # --- User Activity (long-term memory) ---
    if user_activity_bullets:
        sections.append("## User Activity (Long-Term Memory)")
        sections.append(
            "Recent questions from this user across all conversations:"
        )
        sections.extend(user_activity_bullets)
        sections.append("")

    # --- Policy details ---
    meta = data.get("policy", {}) or {}
    if meta:
        sections.append("## Policy Details")
        sections.append(_row(["Field", "Value"]))
        sections.append(_row(["---", "---"]))
        for k, v in meta.items():
            if v:
                sections.append(
                    _row([k.replace("_", " ").title(), str(v)])
                )
        sections.append("")

    # --- Coverage ---
    coverage = data.get("coverage", []) or []
    if coverage:
        sections.append("## Coverage")
        sections.append(_row(["Type", "Limit", "Deductible", "Notes"]))
        sections.append(_row(["---", "---", "---", "---"]))
        for item in coverage:
            sections.append(
                _row(
                    [
                        str(item.get("type", "") or "-"),
                        str(item.get("limit", "") or "-"),
                        str(item.get("deductible", "") or "-"),
                        str(item.get("notes", "") or "-"),
                    ]
                )
            )
        sections.append("")

    # --- Premium ---
    premium = data.get("premium", {}) or {}
    if premium:
        sections.append("## Premium")
        if premium.get("annual"):
            sections.append(
                f"- **Annual (lump sum)**: {premium['annual']}"
            )
        if premium.get("installment_amount") and premium.get(
            "installment_count"
        ):
            sections.append(
                f"- **Installments**: {premium['installment_count']} x "
                f"{premium['installment_amount']}"
            )
        if chart_b64:
            sections.append("")
            sections.append(
                "![Premium Comparison]"
                f"(data:image/png;base64,{chart_b64})"
            )
        sections.append("")

    # --- Claims ---
    claims = data.get("claims", {}) or {}
    if claims:
        sections.append("## Claims Procedure")
        if claims.get("reporting_window"):
            sections.append(
                f"- **Reporting window**: {claims['reporting_window']}"
            )
        docs = claims.get("required_documents", []) or []
        if docs:
            sections.append("- **Required documents**:")
            for d in docs:
                sections.append(f"  - {d}")
        sections.append("")

    # --- Exclusions ---
    exclusions = data.get("exclusions", []) or []
    if exclusions:
        sections.append("## Exclusions")
        for e in exclusions:
            sections.append(f"- {e}")
        sections.append("")

    # --- Sources ---
    if chunks:
        sections.append("## Sources")
        unique_sources: list[str] = []
        seen: set[str] = set()
        for c in chunks:
            if c.source not in seen:
                seen.add(c.source)
                unique_sources.append(c.source)
        for source in unique_sources:
            sections.append(f"- `{source}`")

    return "\n".join(sections)
