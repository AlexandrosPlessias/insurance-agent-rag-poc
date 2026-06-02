"""Phase 9 download endpoints.

GET /reports/{year}.docx -> DOCX bytes
GET /reports/{year}.pdf  -> PDF bytes
GET /reports/{year}.md   -> Markdown text

Each endpoint re-builds the executive annual report from scratch
for the requested year via build_executive_report(year). Since the
report's content is deterministic given (year, csv_sha, git_sha),
the same URL will return functionally-equivalent bytes for the
same source state - the in-flight LLM prose is the only varying
piece. The footer's report_run_id is stable.

Year validation: the year must be in settings.kb_covered_years
(2020 / 2021 / 2022 / 2024 by default). 2023 is the documented gap.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.config import settings
from app.observability.logging import get_logger
from app.reporting.executive import build_executive_report
from app.reporting.writers import render_docx, render_markdown, render_pdf

log = get_logger(__name__)
router = APIRouter()


def _check_year(year: int) -> None:
    covered = list(settings.kb_covered_years)
    if year not in covered:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Year {year} is not covered. Available: {covered}."
            ),
        )


@router.get("/reports/{year}.md")
def get_report_md(year: int) -> Response:
    _check_year(year)
    log.info("GET /reports/%d.md", year)
    doc = build_executive_report(year)
    body = render_markdown(doc)
    return Response(
        content=body,
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition":
                f'attachment; filename="acme_report_{year}.md"',
            "X-Report-Run-Id": doc.cover.report_run_id,
        },
    )


@router.get("/reports/{year}.docx")
def get_report_docx(year: int) -> Response:
    _check_year(year)
    log.info("GET /reports/%d.docx", year)
    doc = build_executive_report(year)
    body = render_docx(doc)
    return Response(
        content=body,
        media_type=(
            "application/vnd.openxmlformats-officedocument."
            "wordprocessingml.document"
        ),
        headers={
            "Content-Disposition":
                f'attachment; filename="acme_report_{year}.docx"',
            "X-Report-Run-Id": doc.cover.report_run_id,
        },
    )


@router.get("/reports/{year}.pdf")
def get_report_pdf(year: int) -> Response:
    _check_year(year)
    log.info("GET /reports/%d.pdf", year)
    doc = build_executive_report(year)
    body = render_pdf(doc)
    return Response(
        content=body,
        media_type="application/pdf",
        headers={
            "Content-Disposition":
                f'attachment; filename="acme_report_{year}.pdf"',
            "X-Report-Run-Id": doc.cover.report_run_id,
        },
    )
