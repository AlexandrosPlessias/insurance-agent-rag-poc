"""assembler + public entry point.

Orchestrates the pipeline:

    collect (Step 3)
        -> CollectedInputs
    narrate (Step 4)
        -> ExecutiveSummarySection
        -> YearlyNarrativeSection
        -> RecommendationsSection
    assemble (here)
        -> ReportDocument

The assembler stitches the narrated sections together with the
deterministic ones (KpiHighlights, Trends, RiskIndicators built by
the collector), computes the reproducibility hash, and produces an
on-screen-Markdown-ready ReportDocument that the Step 6 writers
serialise to MD / DOCX / PDF.

Public entry point: build_executive_report(year). Used by the
report_agent (Step 7) and by the smoke test (Step 9).
"""
from __future__ import annotations

import hashlib
import os
import subprocess
from datetime import datetime, timezone

from agentic_backend.observability.logging import get_logger
from agentic_backend.observability.tracing import get_tracer
from agentic_backend.reporting.executive.collector import CollectedInputs, collect
from agentic_backend.reporting.executive.narrator import (
    narrate_executive_summary,
    narrate_recommendations,
    narrate_yearly_narrative,
)
from agentic_backend.reporting.executive.sections import (
    AppendixSection,
    CoverSection,
    ReportDocument,
)

log = get_logger(__name__)
tracer = get_tracer(__name__)


# ---------------------------------------------------------------------
# Reproducibility hash
# ---------------------------------------------------------------------


def _git_sha_short() -> str:
    """Current HEAD short sha, or 'unknown' if git isn't available.

    A demo run outside a checkout (or with no .git directory) still
    produces a stable run id - it just won't change when the source
    code changes.
    """
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short=8", "HEAD"],
            capture_output=True, text=True, timeout=2,
            cwd=os.path.dirname(os.path.abspath(__file__)),
            check=False,
        )
        if out.returncode == 0:
            return out.stdout.strip() or "unknown"
    except (FileNotFoundError, subprocess.SubprocessError):
        pass
    return "unknown"


def compute_report_run_id(year: int, kpi_csv_sha256: str) -> str:
    """sha256(year + csv_hash + git_sha)[:12].

    Two runs with the same (year, CSV state, source commit) produce
    a byte-identical id. Embedded in the report footer so a reviewer
    can confirm 'this is the same report that was approved last
    quarter' by id alone.
    """
    fingerprint = f"{year}|{kpi_csv_sha256}|{_git_sha_short()}"
    return hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:12]


# ---------------------------------------------------------------------
# Appendix
# ---------------------------------------------------------------------


def _build_appendix_markdown(inputs: CollectedInputs) -> str:
    """Render the appendix KPI table as Markdown.

    Hand-rolled (no pandas to_markdown -> no tabulate dependency).
    Columns are the dimension columns + the 14 numeric metrics
    declared in the schema.
    """
    if not inputs.appendix_kpi_rows:
        return "_(no rows for this year)_"

    rows = inputs.appendix_kpi_rows
    # Stable column order: dimensions first, then metrics.
    cols = [
        "period", "channel", "product_line",
        "policies_in_force", "new_policies", "renewal_rate_pct",
        "gross_written_premium_eur",
        "claims_reported", "claims_paid_eur",
        "avg_claim_settlement_days", "loss_ratio_pct",
        "nps_score", "complaints_count", "fraud_cases_detected",
        "compliance_incidents", "operating_expense_eur",
        "digital_adoption_pct",
    ]
    cols = [c for c in cols if c in rows[0]]

    out: list[str] = []
    out.append("| " + " | ".join(cols) + " |")
    out.append("|" + "|".join(["---"] * len(cols)) + "|")
    for r in rows:
        cells = []
        for c in cols:
            v = r.get(c)
            if v is None or (isinstance(v, float) and v != v):
                cells.append("")
            elif isinstance(v, float):
                cells.append(f"{v:.2f}")
            else:
                cells.append(str(v))
        out.append("| " + " | ".join(cells) + " |")
    return "\n".join(out)


def _build_appendix(inputs: CollectedInputs) -> AppendixSection:
    return AppendixSection(
        kpi_table_markdown=_build_appendix_markdown(inputs),
        cited_chunks=[
            {
                "source": c.source,
                "section": c.section_title or c.section,
                "content": c.content,
            }
            for c in inputs.policy_chunks
        ],
    )


# ---------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------


def build_executive_report(year: int) -> ReportDocument:
    """Generate the executive annual report for `year`.

    Three steps: collect (deterministic, fast), narrate (three LLM
    calls), assemble (deterministic, fast). Wrapped in one outer
    span so an Aspire trace shows the whole pipeline.
    """
    with tracer.start_as_current_span("report.build_executive") as span:
        span.set_attribute("report.year", year)

        # --- collect ---
        inputs = collect(year)
        span.set_attribute("report.compare_to_year", inputs.compare_to_year)
        span.set_attribute(
            "report.csv_sha256", inputs.csv_sha256[:12]
        )

        # --- narrate (3 LLM calls; each fault-tolerant) ---
        executive_summary = narrate_executive_summary(inputs)
        yearly_narrative = narrate_yearly_narrative(inputs)
        recommendations = narrate_recommendations(inputs)

        # --- assemble ---
        run_id = compute_report_run_id(year, inputs.csv_sha256)
        cover = CoverSection(
            year=year,
            generated_on=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            report_run_id=run_id,
            kpi_csv_sha256=inputs.csv_sha256[:12],
        )
        appendix = _build_appendix(inputs)

        doc = ReportDocument(
            year=year,
            cover=cover,
            executive_summary=executive_summary,
            yearly_narrative=yearly_narrative,
            kpi_highlights=inputs.kpi_highlights,
            trends=inputs.trends,
            risk_indicators=inputs.risk_indicators,
            recommendations=recommendations,
            appendix=appendix,
        )

        span.set_attribute("report.run_id", run_id)
        span.set_attribute(
            "report.recommendation_count",
            len(recommendations.items),
        )
        log.info(
            "build_executive_report done: year=%d run_id=%s "
            "recs=%d csv_sha=%s",
            year,
            run_id,
            len(recommendations.items),
            inputs.csv_sha256[:12],
        )
        return doc
