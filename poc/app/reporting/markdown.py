"""Markdown report formatting for policy summaries."""
from datetime import datetime

from app.rag.retriever import RetrievedChunk


def _row(values: list[str]) -> str:
    return "| " + " | ".join(values) + " |"


def build_policy_report(
    data: dict,
    chunks: list[RetrievedChunk],
    chart_b64: str = "",
) -> str:
    """Render a Markdown policy summary with optional embedded chart."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    sections: list[str] = ["# Policy Summary Report", f"*Generated: {now}*", ""]

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
            sections.append(f"- **Annual (lump sum)**: {premium['annual']}")
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
        unique: dict[str, set[int]] = {}
        for c in chunks:
            unique.setdefault(c.source, set()).add(c.page)
        for source, pages in unique.items():
            page_str = ", ".join(str(p) for p in sorted(pages))
            sections.append(f"- `{source}` (pages: {page_str})")

    return "\n".join(sections)
