"""Section + ReportDocument dataclasses for the executive annual report.

These are pure data shapes - no LLM, no pandas, no I/O. They are
the contract every downstream step consumes:

    collector  -> populates the structured inputs on each section
    narrator   -> writes narrative_md on the prose sections
    assemble   -> stitches sections into a ReportDocument and
                  computes report_run_id
    writers    -> markdown / docx / pdf serialise the same
                  ReportDocument

Field-level optionality reflects which step fills what:

  - Cover                       fully populated at assemble time
  - ExecutiveSummary            narrative_md filled by narrator
  - YearlyNarrative             narrative_md filled by narrator
  - KpiHighlights               fully populated by collector (no LLM)
  - TrendsAndVariance           charts populated by collector;
                                  narrative_md filled by narrator
  - RiskIndicators              fully populated by collector +
                                  thresholds.py (no LLM)
  - Recommendations             items filled by narrator with
                                  citation references the collector
                                  pre-resolved
  - Appendix                    fully populated by collector

Floor rule: writers must NEVER hit an unpopulated field. If a step
fails (e.g. narrator can't reach Ollama), the section's
narrative_md falls back to a templated placeholder rather than
leaving the field empty.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

# ---------------------------------------------------------------------
# Shared value types
# ---------------------------------------------------------------------

Severity = Literal["green", "amber", "red"]


# ---------------------------------------------------------------------
# Section dataclasses
# ---------------------------------------------------------------------


@dataclass(frozen=True)
class CoverSection:
    """Front matter. Fully populated at assemble time."""

    year: int
    generated_on: str          # ISO-8601 UTC date
    report_run_id: str         # sha256(year + kpi_csv_hash + git_sha)[:12]
    kpi_csv_sha256: str        # 12-char prefix for display


@dataclass
class ExecutiveSummarySection:
    """LLM-written 4-6 sentence top-of-report narrative.

    Inputs come from the collector (the same numbers the rest of
    the report uses), so the LLM can ground its summary without
    needing the whole document.
    """

    headline_metrics: dict     # e.g. {"gwp_yoy_pct": 24.4, "loss_ratio": 39.5}
    narrative_md: str = ""    # filled by narrator


@dataclass
class YearlyNarrativeSection:
    """One paragraph per business pillar. LLM-written, grounded in
    the collector's structured inputs + a handful of policy chunks
    from RAG retrieval."""

    pillars: list[str] = field(
        default_factory=lambda: [
            "commercial", "claims", "customer", "compliance",
        ]
    )
    inputs: dict = field(default_factory=dict)
    chunks: list[dict] = field(default_factory=list)
    narrative_md: str = ""    # filled by narrator


@dataclass
class KpiHighlight:
    label: str                 # human-friendly metric name
    value_str: str             # already formatted (e.g. "€26.3M")
    yoy_delta_str: str = ""   # signed delta vs previous covered year
    yoy_pct_str: str = ""     # signed percentage (e.g. "+24.4%")


@dataclass
class KpiHighlightsSection:
    """2x4 KPI grid. Pre-formatted, no LLM."""

    items: list[KpiHighlight] = field(default_factory=list)
    compare_to_year: int = 0   # the year we computed YoY against


@dataclass
class TrendChart:
    title: str
    png_base64: str            # data: URI body (without prefix)
    metric: str = ""           # source metric name for the audit row


@dataclass
class TrendsAndVarianceSection:
    """3-5 charts (GWP, renewal rate, claims paid, NPS, digital
    adoption) + optional LLM-written variance commentary."""

    charts: list[TrendChart] = field(default_factory=list)
    narrative_md: str = ""    # optional - filled by narrator if on


@dataclass
class RiskIndicator:
    label: str                 # short ("Claims pressure")
    value_str: str             # already formatted ("0.92")
    severity: Severity
    note: str = ""             # one-line context for the reader


@dataclass
class RiskIndicatorsSection:
    """Deterministic green / amber / red bands. Severity comes from
    thresholds.py, not the LLM."""

    indicators: list[RiskIndicator] = field(default_factory=list)


@dataclass
class Recommendation:
    title: str                 # action verb sentence
    rationale_md: str          # grounding text
    metric_anchor: str = ""    # which KPI triggered the action
    chunk_anchor: str = ""     # source / section reference from RAG


@dataclass
class RecommendationsSection:
    """3-5 actionable bullets. LLM-written, with both a metric anchor
    AND a policy-chunk anchor per recommendation so the reader can
    verify both the trigger and the supporting clause."""

    items: list[Recommendation] = field(default_factory=list)


@dataclass
class AppendixSection:
    """Full KPI table + every cited chunk. Pure data, no LLM."""

    kpi_table_markdown: str = ""
    cited_chunks: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------
# Container
# ---------------------------------------------------------------------


@dataclass
class ReportDocument:
    """The intermediate shape every writer (markdown / docx / pdf)
    consumes. Sections are stored on named attributes (not a list)
    so writers can build their own ordering / formatting without
    string-matching section headings."""

    year: int
    cover: CoverSection
    executive_summary: ExecutiveSummarySection
    yearly_narrative: YearlyNarrativeSection
    kpi_highlights: KpiHighlightsSection
    trends: TrendsAndVarianceSection
    risk_indicators: RiskIndicatorsSection
    recommendations: RecommendationsSection
    appendix: AppendixSection

    def as_audit_payload(self) -> dict:
        """Cheap, JSON-safe summary for the report.generate audit row.

        Carries the bits a compliance reviewer wants countable - the
        run id, the source CSV hash, the year, the number of risk
        flags by severity, the count of recommendations - WITHOUT
        the chart PNG bytes (those would balloon the audit row).
        """
        sev_counts: dict[Severity, int] = {
            "green": 0, "amber": 0, "red": 0,
        }
        for ind in self.risk_indicators.indicators:
            sev_counts[ind.severity] = sev_counts.get(ind.severity, 0) + 1
        return {
            "year": self.year,
            "report_run_id": self.cover.report_run_id,
            "kpi_csv_sha256": self.cover.kpi_csv_sha256,
            "generated_on": self.cover.generated_on,
            "kpi_count": len(self.kpi_highlights.items),
            "trend_chart_count": len(self.trends.charts),
            "risk_severity_counts": sev_counts,
            "recommendation_count": len(self.recommendations.items),
            "appendix_chunk_count": len(self.appendix.cited_chunks),
        }
