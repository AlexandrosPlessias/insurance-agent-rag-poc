"""Markdown writer for the executive annual report.

Renders a ReportDocument into a single Markdown string. Charts are
embedded as base64 data URIs so the same string can be (a) shown
inline in the React UI, (b) saved as a .md file and viewed in any
Markdown reader, and (c) used as the source for the PDF writer's
HTML-ish layout.

Pure-string output, no third-party dependency.
"""
from __future__ import annotations

from agentic_backend.reporting.executive.sections import ReportDocument, Severity

# Unicode dots used as severity badges in the Markdown. These render
# in most browsers; the DOCX/PDF writers use real coloured shapes.
_SEVERITY_BADGE: dict[Severity, str] = {
    "green": "🟢",
    "amber": "🟡",
    "red":   "🔴",
}


def render_markdown(doc: ReportDocument) -> str:
    out: list[str] = []

    # --- Cover -----------------------------------------------------
    out.append(f"# Executive Annual Report · {doc.year}")
    out.append("")
    out.append(
        f"_ACME Insurances · generated {doc.cover.generated_on} · "
        f"run id `{doc.cover.report_run_id}` · "
        f"source CSV sha256 `{doc.cover.kpi_csv_sha256}`_"
    )
    out.append("")

    # --- Executive Summary ----------------------------------------
    out.append("## Executive summary")
    out.append("")
    out.append(doc.executive_summary.narrative_md or "_(no summary)_")
    out.append("")

    # --- Yearly Performance Narrative -----------------------------
    out.append("## Yearly performance narrative")
    out.append("")
    out.append(doc.yearly_narrative.narrative_md or "_(no narrative)_")
    out.append("")

    # --- KPI Highlights -------------------------------------------
    out.append("## KPI highlights")
    out.append("")
    out.append(
        f"_Year-on-year comparisons reference "
        f"{doc.kpi_highlights.compare_to_year}._"
    )
    out.append("")
    out.append("| Metric | Value | YoY | YoY % |")
    out.append("|---|---|---|---|")
    for item in doc.kpi_highlights.items:
        out.append(
            f"| {item.label} | **{item.value_str}** | "
            f"{item.yoy_delta_str} | {item.yoy_pct_str} |"
        )
    out.append("")

    # --- Trends & Variance ----------------------------------------
    out.append("## Trends & variance")
    out.append("")
    for chart in doc.trends.charts:
        out.append(f"**{chart.title}**")
        out.append("")
        out.append(
            f"![{chart.title}]"
            f"(data:image/png;base64,{chart.png_base64})"
        )
        out.append("")
    if doc.trends.narrative_md:
        out.append(doc.trends.narrative_md)
        out.append("")

    # --- Risk & Issue Indicators ----------------------------------
    out.append("## Risk & issue indicators")
    out.append("")
    out.append("| Indicator | Value | Severity | Note |")
    out.append("|---|---|---|---|")
    for ind in doc.risk_indicators.indicators:
        badge = _SEVERITY_BADGE.get(ind.severity, "")
        out.append(
            f"| {ind.label} | {ind.value_str} | "
            f"{badge} **{ind.severity.upper()}** | {ind.note} |"
        )
    out.append("")

    # --- Actionable Recommendations -------------------------------
    out.append("## Actionable recommendations")
    out.append("")
    if not doc.recommendations.items:
        out.append("_(no recommendations)_")
    for i, rec in enumerate(doc.recommendations.items, start=1):
        out.append(f"**{i}. {rec.title}**")
        out.append("")
        if rec.rationale_md:
            out.append(rec.rationale_md)
            out.append("")
        anchors = []
        if rec.metric_anchor:
            anchors.append(f"metric: `{rec.metric_anchor}`")
        if rec.chunk_anchor:
            anchors.append(f"policy: _{rec.chunk_anchor}_")
        if anchors:
            out.append("_" + "  ·  ".join(anchors) + "_")
            out.append("")

    # --- Appendix --------------------------------------------------
    out.append("## Appendix · monthly KPI table")
    out.append("")
    out.append(doc.appendix.kpi_table_markdown or "_(no rows)_")
    out.append("")

    if doc.appendix.cited_chunks:
        out.append("### Cited policy chunks")
        out.append("")
        for i, ch in enumerate(doc.appendix.cited_chunks, start=1):
            out.append(
                f"**[{i}] {ch.get('source', '')}  ·  "
                f"{ch.get('section', '')}**"
            )
            out.append("")
            body = (ch.get("content") or "")[:600]
            if body:
                out.append(f"> {body}")
                out.append("")

    # --- Footer ----------------------------------------------------
    out.append("---")
    out.append(
        f"_Report id `{doc.cover.report_run_id}` · "
        f"CSV `{doc.cover.kpi_csv_sha256}`_"
    )

    return "\n".join(out)
