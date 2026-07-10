"""executive annual report.

Section-by-section pipeline (collector -> narrator -> assemble ->
render) over the KPI dataset + RAG chunks. Public
surface:

    from agentic_backend.reporting.executive import (
        ReportDocument,
        build_executive_report,   # entry point used by report_agent
    )

Severity for risk flags is deterministic (thresholds.py) - the
single point of LLM-free trust in the whole report.
"""
from agentic_backend.reporting.executive.builder import (
    build_executive_report,
    compute_report_run_id,
)
from agentic_backend.reporting.executive.sections import (
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
