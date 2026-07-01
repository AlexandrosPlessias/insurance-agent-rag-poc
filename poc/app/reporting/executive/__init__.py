"""Phase 9 executive annual report.

Section-by-section pipeline (collector -> narrator -> assemble ->
render) over the Phase 8 KPI dataset + Phase 1 RAG chunks. Public
surface:

    from app.reporting.executive import (
        ReportDocument,
        build_executive_report,   # entry point used by report_agent
    )

Severity for risk flags is deterministic (thresholds.py) - the
single point of LLM-free trust in the whole report.
"""
from app.reporting.executive.builder import (
    build_executive_report,
    compute_report_run_id,
)
from app.reporting.executive.sections import (
    AppendixSection,
    CoverSection,
    ExecutiveSummarySection,
    KpiHighlight,
    KpiHighlightsSection,
    Recommendation,
    RecommendationsSection,
    ReportDocument,
    RiskIndicator,
    RiskIndicatorsSection,
    Severity,
    TrendChart,
    TrendsAndVarianceSection,
    YearlyNarrativeSection,
)

__all__ = [
    "build_executive_report",
    "compute_report_run_id",
    "ReportDocument",
    "CoverSection",
    "ExecutiveSummarySection",
    "YearlyNarrativeSection",
    "KpiHighlightsSection",
    "KpiHighlight",
    "TrendsAndVarianceSection",
    "TrendChart",
    "RiskIndicatorsSection",
    "RiskIndicator",
    "Severity",
    "RecommendationsSection",
    "Recommendation",
    "AppendixSection",
]
