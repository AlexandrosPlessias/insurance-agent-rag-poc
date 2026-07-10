"""PDF writer for the executive annual report.

Renders a ReportDocument into a PDF byte-string via reportlab's
SimpleDocTemplate (Platypus flowables). Chose reportlab over
weasyprint to avoid the GTK system dependency that weasyprint
needs on WSL; trade-off is more verbose layout code, but the
report shape is simple enough that it doesn't matter.

reportlab is imported lazily inside render_pdf so the rest of
the app doesn't pay the cost when no PDF is requested.
"""
from __future__ import annotations

import base64
import io

from agentic_backend.reporting.executive.sections import ReportDocument, Severity

_SEVERITY_HEX: dict[Severity, str] = {
    "green": "#2e8b57",
    "amber": "#cc8800",
    "red":   "#c13e3e",
}


def render_pdf(doc: ReportDocument) -> bytes:
    # Lazy imports - the heavy reportlab stack only loads when a
    # PDF is actually requested.
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import (
        getSampleStyleSheet,
        ParagraphStyle,
    )
    from reportlab.lib.units import inch, mm
    from reportlab.platypus import (
        Image,
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    styles = getSampleStyleSheet()
    body = ParagraphStyle(
        "body",
        parent=styles["BodyText"],
        fontSize=10,
        leading=13,
        spaceAfter=4,
    )
    small = ParagraphStyle(
        "small",
        parent=body,
        fontSize=8,
        textColor=colors.HexColor("#666"),
        spaceAfter=8,
    )
    title = ParagraphStyle(
        "title",
        parent=styles["Title"],
        fontSize=20,
        spaceAfter=4,
    )
    h1 = ParagraphStyle(
        "h1",
        parent=styles["Heading1"],
        fontSize=14,
        spaceBefore=10,
        spaceAfter=6,
    )

    flowables: list = []

    # --- Cover -----------------------------------------------------
    flowables.append(
        Paragraph(f"Executive Annual Report · {doc.year}", title)
    )
    flowables.append(Paragraph(
        f"ACME Insurances &nbsp;·&nbsp; generated "
        f"{doc.cover.generated_on} &nbsp;·&nbsp; run id "
        f"<font face='Courier'>{doc.cover.report_run_id}</font> "
        f"&nbsp;·&nbsp; source CSV "
        f"<font face='Courier'>{doc.cover.kpi_csv_sha256}</font>",
        small,
    ))
    flowables.append(Spacer(1, 6))

    # --- Executive summary ----------------------------------------
    flowables.append(Paragraph("Executive summary", h1))
    flowables.append(Paragraph(
        (doc.executive_summary.narrative_md or "(no summary)")
        .replace("\n", "<br/>"),
        body,
    ))

    # --- Yearly narrative -----------------------------------------
    flowables.append(Paragraph("Yearly performance narrative", h1))
    for para in (doc.yearly_narrative.narrative_md or "").split("\n\n"):
        if para.strip():
            flowables.append(Paragraph(
                para.strip().replace("\n", "<br/>").replace(
                    "**", "<b>", 1
                ).replace("**", "</b>", 1),
                body,
            ))

    # --- KPI highlights -------------------------------------------
    flowables.append(Paragraph("KPI highlights", h1))
    flowables.append(Paragraph(
        f"Year-on-year comparisons reference "
        f"{doc.kpi_highlights.compare_to_year}.",
        small,
    ))
    table_rows = [["Metric", "Value", "YoY", "YoY %"]] + [
        [it.label, it.value_str, it.yoy_delta_str, it.yoy_pct_str]
        for it in doc.kpi_highlights.items
    ]
    tbl = Table(
        table_rows,
        colWidths=[2.6 * inch, 1.4 * inch, 1.4 * inch, 1.0 * inch],
        hAlign="LEFT",
    )
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0d3b66")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cccccc")),
    ]))
    flowables.append(tbl)

    # --- Trends ----------------------------------------------------
    flowables.append(Paragraph("Trends & variance", h1))
    for chart in doc.trends.charts:
        flowables.append(Paragraph(f"<b>{chart.title}</b>", body))
        img_buf = io.BytesIO(base64.b64decode(chart.png_base64))
        img = Image(img_buf, width=5.2 * inch, height=2.6 * inch)
        flowables.append(img)
        flowables.append(Spacer(1, 4))

    # --- Risk indicators ------------------------------------------
    flowables.append(Paragraph("Risk & issue indicators", h1))
    rrows = [["Indicator", "Value", "Severity", "Note"]] + [
        [
            ind.label, ind.value_str, ind.severity.upper(), ind.note
        ]
        for ind in doc.risk_indicators.indicators
    ]
    rtable_style = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0d3b66")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cccccc")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]
    # Per-row severity colouring on the third column.
    for i, ind in enumerate(doc.risk_indicators.indicators, start=1):
        hex_col = _SEVERITY_HEX.get(ind.severity, "#000000")
        rtable_style.append(
            ("TEXTCOLOR", (2, i), (2, i), colors.HexColor(hex_col))
        )
        rtable_style.append(
            ("FONTNAME", (2, i), (2, i), "Helvetica-Bold")
        )
    rtable = Table(
        rrows,
        colWidths=[1.8 * inch, 1.0 * inch, 0.9 * inch, 2.7 * inch],
        hAlign="LEFT",
    )
    rtable.setStyle(TableStyle(rtable_style))
    flowables.append(rtable)

    # --- Recommendations ------------------------------------------
    flowables.append(Paragraph("Actionable recommendations", h1))
    if not doc.recommendations.items:
        flowables.append(Paragraph("(no recommendations)", body))
    for i, rec in enumerate(doc.recommendations.items, start=1):
        flowables.append(Paragraph(
            f"<b>{i}. {rec.title}</b>", body
        ))
        if rec.rationale_md:
            flowables.append(Paragraph(rec.rationale_md, body))
        anchors = []
        if rec.metric_anchor:
            anchors.append(f"metric: <i>{rec.metric_anchor}</i>")
        if rec.chunk_anchor:
            anchors.append(f"policy: <i>{rec.chunk_anchor}</i>")
        if anchors:
            flowables.append(Paragraph(
                " &nbsp;·&nbsp; ".join(anchors), small
            ))

    # --- Appendix --------------------------------------------------
    flowables.append(PageBreak())
    flowables.append(Paragraph("Appendix · monthly KPI table", h1))
    if doc.appendix.kpi_table_markdown:
        # Render the appendix Markdown verbatim as monospaced text -
        # we don't have a Markdown parser for reportlab and the
        # table is reference material anyway.
        for line in doc.appendix.kpi_table_markdown.splitlines():
            flowables.append(Paragraph(
                f"<font face='Courier' size='6'>{_escape(line)}</font>",
                body,
            ))
    if doc.appendix.cited_chunks:
        flowables.append(Paragraph("Cited policy chunks", h1))
        for i, ch in enumerate(doc.appendix.cited_chunks, start=1):
            flowables.append(Paragraph(
                f"<b>[{i}] {ch.get('source', '')} · "
                f"{ch.get('section', '')}</b>",
                body,
            ))
            body_text = (ch.get("content") or "")[:600]
            if body_text:
                flowables.append(Paragraph(
                    _escape(body_text), body,
                ))

    # --- Footer (rendered as a final paragraph; no native footer) -
    flowables.append(Spacer(1, 10))
    flowables.append(Paragraph(
        f"Report id <font face='Courier'>"
        f"{doc.cover.report_run_id}</font> &nbsp;·&nbsp; "
        f"CSV <font face='Courier'>"
        f"{doc.cover.kpi_csv_sha256}</font>",
        small,
    ))

    buf = io.BytesIO()
    SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm,
        title=f"Executive Annual Report {doc.year}",
        author="ACME Insurances",
    ).build(flowables)
    return buf.getvalue()


def _escape(text: str) -> str:
    """Minimal XML-escape so reportlab's Paragraph parser doesn't
    choke on stray ampersands or angle brackets in chunk text."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
