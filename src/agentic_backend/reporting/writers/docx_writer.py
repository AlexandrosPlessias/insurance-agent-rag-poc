"""DOCX writer for the executive annual report.

Renders a ReportDocument into a Word .docx file using python-docx.
Returns bytes so the caller can save / stream the document
directly. Embedding follows the same section order as the Markdown
writer; chart PNGs are decoded from base64 and added as inline
images sized to the page width.

python-docx is imported lazily so the rest of the app doesn't pay
the import cost when no executive report is requested.
"""
from __future__ import annotations

import base64
import io

from agentic_backend.reporting.executive.sections import ReportDocument, Severity

# Severity coloured text used inside the risk-indicators table. The
# DOCX writer doesn't currently emit table-cell shading; coloured
# run text + the severity word makes the band obvious.
_SEVERITY_RGB: dict[Severity, tuple[int, int, int]] = {
    "green": (0x2e, 0x8b, 0x57),   # sea green
    "amber": (0xcc, 0x88, 0x00),   # amber
    "red":   (0xc1, 0x3e, 0x3e),   # red
}


def render_docx(doc: ReportDocument) -> bytes:
    # Lazy imports so unrelated paths don't pay the cost.
    from docx import Document
    from docx.shared import Inches, Pt, RGBColor

    d = Document()

    # --- Cover -----------------------------------------------------
    d.add_heading(f"Executive Annual Report · {doc.year}", level=0)
    p = d.add_paragraph()
    run = p.add_run(
        f"ACME Insurances · generated {doc.cover.generated_on} · "
        f"run id {doc.cover.report_run_id} · "
        f"source CSV sha256 {doc.cover.kpi_csv_sha256}"
    )
    run.italic = True
    run.font.size = Pt(9)

    # --- Executive summary ----------------------------------------
    d.add_heading("Executive summary", level=1)
    d.add_paragraph(
        doc.executive_summary.narrative_md or "(no summary)"
    )

    # --- Yearly narrative -----------------------------------------
    d.add_heading("Yearly performance narrative", level=1)
    for para in (doc.yearly_narrative.narrative_md or "").split("\n\n"):
        if para.strip():
            d.add_paragraph(para.strip())

    # --- KPI highlights -------------------------------------------
    d.add_heading("KPI highlights", level=1)
    note = d.add_paragraph()
    note_run = note.add_run(
        f"Year-on-year comparisons reference "
        f"{doc.kpi_highlights.compare_to_year}."
    )
    note_run.italic = True
    note_run.font.size = Pt(9)

    rows = [("Metric", "Value", "YoY", "YoY %")] + [
        (it.label, it.value_str, it.yoy_delta_str, it.yoy_pct_str)
        for it in doc.kpi_highlights.items
    ]
    table = d.add_table(rows=len(rows), cols=4)
    table.style = "Light Grid"
    for r_idx, row in enumerate(rows):
        for c_idx, val in enumerate(row):
            cell = table.cell(r_idx, c_idx)
            cell.text = val
            if r_idx == 0:
                for run in cell.paragraphs[0].runs:
                    run.bold = True

    # --- Trends & variance ----------------------------------------
    d.add_heading("Trends & variance", level=1)
    for chart in doc.trends.charts:
        d.add_paragraph(chart.title).runs[0].bold = True
        img = io.BytesIO(base64.b64decode(chart.png_base64))
        d.add_picture(img, width=Inches(5.5))
    if doc.trends.narrative_md:
        d.add_paragraph(doc.trends.narrative_md)

    # --- Risk & issue indicators ----------------------------------
    d.add_heading("Risk & issue indicators", level=1)
    rrows = [("Indicator", "Value", "Severity", "Note")] + [
        (ind.label, ind.value_str, ind.severity.upper(), ind.note)
        for ind in doc.risk_indicators.indicators
    ]
    rtable = d.add_table(rows=len(rrows), cols=4)
    rtable.style = "Light Grid"
    for r_idx, row in enumerate(rrows):
        for c_idx, val in enumerate(row):
            cell = rtable.cell(r_idx, c_idx)
            cell.text = val
            if r_idx == 0:
                for run in cell.paragraphs[0].runs:
                    run.bold = True
            elif c_idx == 2:
                # Colour the severity word per band.
                severity = (
                    doc.risk_indicators.indicators[r_idx - 1].severity
                )
                rgb = _SEVERITY_RGB.get(severity)
                if rgb:
                    for run in cell.paragraphs[0].runs:
                        run.font.color.rgb = RGBColor(*rgb)
                        run.bold = True

    # --- Recommendations ------------------------------------------
    d.add_heading("Actionable recommendations", level=1)
    if not doc.recommendations.items:
        d.add_paragraph("(no recommendations)")
    for i, rec in enumerate(doc.recommendations.items, start=1):
        d.add_paragraph(f"{i}. {rec.title}").runs[0].bold = True
        if rec.rationale_md:
            d.add_paragraph(rec.rationale_md)
        if rec.metric_anchor or rec.chunk_anchor:
            anchors = []
            if rec.metric_anchor:
                anchors.append(f"metric: {rec.metric_anchor}")
            if rec.chunk_anchor:
                anchors.append(f"policy: {rec.chunk_anchor}")
            p = d.add_paragraph()
            r = p.add_run("  ·  ".join(anchors))
            r.italic = True
            r.font.size = Pt(9)

    # --- Appendix --------------------------------------------------
    d.add_heading("Appendix · monthly KPI table", level=1)
    # We render the monthly rows as a compact table - shrink to fit
    # the page by selecting a stable subset of columns.
    appendix_rows = doc.appendix.cited_chunks  # noqa - kept for clarity
    appendix_md = doc.appendix.kpi_table_markdown
    if appendix_md:
        # python-docx has no markdown table parser; embed as
        # monospaced text so the analyst can copy-paste / read it.
        para = d.add_paragraph()
        run = para.add_run(appendix_md)
        run.font.name = "Consolas"
        run.font.size = Pt(7)

    if doc.appendix.cited_chunks:
        d.add_heading("Cited policy chunks", level=2)
        for i, ch in enumerate(doc.appendix.cited_chunks, start=1):
            head = d.add_paragraph()
            head_run = head.add_run(
                f"[{i}] {ch.get('source', '')} · "
                f"{ch.get('section', '')}"
            )
            head_run.bold = True
            body = (ch.get("content") or "")[:600]
            if body:
                d.add_paragraph(body)

    # --- Footer ----------------------------------------------------
    footer = d.add_paragraph()
    footer_run = footer.add_run(
        f"Report id {doc.cover.report_run_id} · "
        f"CSV {doc.cover.kpi_csv_sha256}"
    )
    footer_run.italic = True
    footer_run.font.size = Pt(8)

    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()
