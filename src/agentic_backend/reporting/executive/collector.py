"""collector.

Runs the KPI Operations + retrieves policy chunks the report sections
will be built from. All deterministic - no LLM here. The collector
populates everything the writers can render WITHOUT a narrator call,
plus the structured inputs the narrator (Step 4) needs to ground its
prose without inventing numbers.

Single entry point :func:`collect`. Output is a CollectedInputs
dataclass; the assembler (Step 5) stitches it into a ReportDocument.
"""
from __future__ import annotations

import base64
import io
from dataclasses import dataclass, field

from agentic_backend.data import (
    Filters,
    KpiDataset,
    Operation,
    OperationViolation,
    execute,
    get_dataset,
)
from agentic_backend.observability.logging import get_logger
from agentic_backend.rag.retriever import RetrievedChunk, retrieve
from agentic_backend.reporting.executive.sections import (
    KpiHighlight,
    KpiHighlightsSection,
    RiskIndicatorsSection,
    TrendChart,
    TrendsAndVarianceSection,
)
from agentic_backend.reporting.executive.thresholds import (
    complaints_yoy_indicator,
    compliance_incidents_indicator,
    fraud_yoy_indicator,
    loss_ratio_indicator,
    settlement_drift_indicator,
)

log = get_logger(__name__)

# Metrics we surface in the KPI grid (flow + rate). Per-metric
# formatter helps render value_str / yoy_delta_str cleanly.
_KPI_GRID: list[tuple[str, str, str]] = [
    # (metric_name, label, format_kind)
    ("gross_written_premium_eur", "Gross written premium", "eur"),
    ("new_policies",              "New policies",           "int"),
    ("policies_in_force",         "Policies in force",      "int_eop"),
    ("renewal_rate_pct",          "Renewal rate",           "pct"),
    ("claims_paid_eur",           "Claims paid",            "eur"),
    ("loss_ratio_pct",            "Loss ratio",             "pct"),
    ("nps_score",                 "NPS",                    "score"),
    ("digital_adoption_pct",      "Digital adoption",       "pct"),
]

# Metrics that get a trend chart (one line per year).
_TREND_METRICS: list[tuple[str, str]] = [
    ("gross_written_premium_eur", "Gross written premium (€)"),
    ("renewal_rate_pct",          "Renewal rate (%)"),
    ("claims_paid_eur",           "Claims paid (€)"),
    ("nps_score",                 "Net Promoter Score"),
    ("digital_adoption_pct",      "Digital adoption (%)"),
]

# How many policy chunks to pull for the narrator's grounding.
_NARRATIVE_CHUNK_K = 6


@dataclass
class CollectedInputs:
    """Everything the assembler needs except the LLM-narrated text.

    Carries the headline numbers used by the executive summary, the
    full KPI grid, trend charts, risk indicators (already severity-
    classified), and a small set of policy chunks for the narrator
    to ground its prose against.
    """

    year: int
    compare_to_year: int
    csv_sha256: str

    # Pre-rendered sections (writers can drop these in as-is).
    kpi_highlights: KpiHighlightsSection
    trends: TrendsAndVarianceSection
    risk_indicators: RiskIndicatorsSection

    # Structured inputs the narrator binds prose to.
    headline_metrics: dict = field(default_factory=dict)
    yearly_pillar_inputs: dict = field(default_factory=dict)
    policy_chunks: list[RetrievedChunk] = field(default_factory=list)

    # Raw KPI table for the appendix (Markdown rendered later).
    appendix_kpi_rows: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------
# Aggregation helpers
# ---------------------------------------------------------------------


def _sum_metric(metric: str, year: int) -> float | None:
    try:
        r = execute(Operation(
            metric=metric, aggregation="sum",
            filters=Filters(year=[year]),
        ))
        return float(r.result.iloc[0][metric])
    except OperationViolation as exc:
        log.warning(
            "collect: sum(%s) %d refused (%s)",
            metric, year, exc.reason,
        )
        return None


def _weighted_mean_metric(metric: str, year: int) -> float | None:
    try:
        r = execute(Operation(
            metric=metric, aggregation="weighted_mean",
            filters=Filters(year=[year]),
        ))
        return float(r.result.iloc[0][metric])
    except OperationViolation as exc:
        log.warning(
            "collect: wmean(%s) %d refused (%s)",
            metric, year, exc.reason,
        )
        return None


def _mean_metric(metric: str, year: int) -> float | None:
    try:
        r = execute(Operation(
            metric=metric, aggregation="mean",
            filters=Filters(year=[year]),
        ))
        return float(r.result.iloc[0][metric])
    except OperationViolation as exc:
        log.warning(
            "collect: mean(%s) %d refused (%s)",
            metric, year, exc.reason,
        )
        return None


def _agg_metric(metric: str, year: int, agg: str) -> float | None:
    """Dispatch on the chosen aggregation kind."""
    if agg == "weighted_mean":
        return _weighted_mean_metric(metric, year)
    if agg == "sum":
        return _sum_metric(metric, year)
    if agg == "mean":
        return _mean_metric(metric, year)
    # Anything else - fall back to the executor directly.
    try:
        r = execute(Operation(
            metric=metric, aggregation=agg,
            filters=Filters(year=[year]),
        ))
        return float(r.result.iloc[0][metric])
    except OperationViolation as exc:
        log.warning(
            "collect: %s(%s) %d refused (%s)",
            agg, metric, year, exc.reason,
        )
        return None


def _previous_covered_year(year: int, ds: KpiDataset) -> int:
    """The nearest covered year BELOW `year`. For 2024 -> 2022
    because 2023 is the gap. For 2020 returns 2020 (no prior;
    YoY delta will be 0)."""
    below = [y for y in ds.covered_years() if y < year]
    return max(below) if below else year


# ---------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------


def _fmt(value: float | None, kind: str) -> str:
    if value is None:
        return "n/a"
    if kind == "eur":
        if abs(value) >= 1_000_000:
            return f"€{value / 1_000_000:.2f}M"
        if abs(value) >= 1_000:
            return f"€{value / 1_000:.1f}k"
        return f"€{value:.0f}"
    if kind == "pct":
        return f"{value:.1f}%"
    if kind == "int":
        return f"{int(round(value)):,}"
    if kind == "int_eop":
        # End-of-period stock - take the avg over the period or
        # display the mean (collector calls weighted_mean below).
        return f"{int(round(value)):,}"
    if kind == "score":
        return f"{value:+.0f}"
    return f"{value:.1f}"


def _fmt_delta(
    curr: float | None, prev: float | None, kind: str,
) -> tuple[str, str]:
    """Returns (yoy_delta_str, yoy_pct_str)."""
    if curr is None or prev is None or prev == 0:
        return ("", "")
    delta = curr - prev
    sign = "+" if delta >= 0 else "-"
    pct = (delta / abs(prev)) * 100
    pct_sign = "+" if pct >= 0 else "-"
    if kind == "eur":
        delta_str = (
            f"{sign}€{abs(delta) / 1_000_000:.2f}M"
            if abs(delta) >= 1_000_000
            else f"{sign}€{abs(delta) / 1_000:.1f}k"
        )
    elif kind == "pct":
        delta_str = f"{sign}{abs(delta):.1f} pp"   # percentage POINTS
    elif kind == "score":
        delta_str = f"{sign}{abs(delta):.0f}"
    else:
        delta_str = f"{sign}{abs(delta):,.0f}"
    return delta_str, f"{pct_sign}{abs(pct):.1f}%"


def _pick_aggregation(metric: str) -> str:
    """Pick a sensible aggregation given the metric's declared kind.

    Preference order:
      weighted_mean  for rate / snapshot metrics that declare it
      sum            for flow metrics
      mean           for stock metrics (sum is illegal across periods)
    """
    valid = get_dataset().valid_aggregations(metric)
    if "weighted_mean" in valid:
        return "weighted_mean"
    if "sum" in valid:
        return "sum"
    return "mean"


def _build_kpi_highlights(
    year: int, prev_year: int,
) -> KpiHighlightsSection:
    items: list[KpiHighlight] = []
    for metric, label, kind in _KPI_GRID:
        agg = _pick_aggregation(metric)
        curr = _agg_metric(metric, year, agg)
        prev = _agg_metric(metric, prev_year, agg)
        delta_str, pct_str = _fmt_delta(curr, prev, kind)
        items.append(KpiHighlight(
            label=label,
            value_str=_fmt(curr, kind),
            yoy_delta_str=delta_str,
            yoy_pct_str=pct_str,
        ))
    return KpiHighlightsSection(items=items, compare_to_year=prev_year)


def _render_trend_chart(metric: str, title: str, ds: KpiDataset) -> str:
    """Build a small matplotlib PNG (base64-encoded) for one metric
    across all covered years. Returns the base64 body only - the
    writers add the `data:image/png;base64,` prefix at render time."""
    # Lazy import to avoid the heavy matplotlib startup cost when
    # the executive report isn't being generated.
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    years = ds.covered_years()
    valid = ds.valid_aggregations(metric)
    agg = (
        "weighted_mean" if "weighted_mean" in valid
        else "sum" if "sum" in valid
        else "mean"
    )
    series: list[float] = []
    for y in years:
        val = (
            _weighted_mean_metric(metric, y)
            if agg == "weighted_mean"
            else _sum_metric(metric, y)
        )
        series.append(val if val is not None else 0.0)

    fig, ax = plt.subplots(figsize=(5.2, 2.6), dpi=120)
    ax.plot(years, series, marker="o", color="#1d6fa5")
    ax.set_title(title, fontsize=10)
    ax.grid(alpha=.3)
    ax.tick_params(labelsize=8)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _build_trends(ds: KpiDataset) -> TrendsAndVarianceSection:
    charts = [
        TrendChart(
            title=title,
            png_base64=_render_trend_chart(metric, title, ds),
            metric=metric,
        )
        for metric, title in _TREND_METRICS
    ]
    return TrendsAndVarianceSection(charts=charts)


def _build_risk_indicators(year: int, prev_year: int) -> RiskIndicatorsSection:
    """Wire the deterministic threshold builders to the collected numbers."""
    loss_ratio = _weighted_mean_metric("loss_ratio_pct", year) or 0.0

    curr_settle = _weighted_mean_metric("avg_claim_settlement_days", year)
    prev_settle = _weighted_mean_metric("avg_claim_settlement_days", prev_year)
    settle_drift = (
        (curr_settle - prev_settle)
        if (curr_settle is not None and prev_settle is not None)
        else 0.0
    )

    def _yoy_pct(metric: str) -> float:
        curr = _sum_metric(metric, year) or 0.0
        prev = _sum_metric(metric, prev_year)
        if not prev:
            return 0.0
        return ((curr - prev) / prev) * 100

    complaints_yoy = _yoy_pct("complaints_count")
    fraud_yoy = _yoy_pct("fraud_cases_detected")
    compliance = int(_sum_metric("compliance_incidents", year) or 0)

    return RiskIndicatorsSection(indicators=[
        loss_ratio_indicator(loss_ratio),
        settlement_drift_indicator(settle_drift),
        complaints_yoy_indicator(complaints_yoy),
        fraud_yoy_indicator(fraud_yoy),
        compliance_incidents_indicator(compliance),
    ])


def _build_headline_metrics(year: int, prev_year: int) -> dict:
    """Compact numeric dict the executive summary narrator binds to.

    Carries the same numbers the rest of the report uses, so the
    narrator can't invent contradicting figures.
    """
    gwp = _sum_metric("gross_written_premium_eur", year) or 0
    gwp_prev = _sum_metric("gross_written_premium_eur", prev_year) or 0
    loss_ratio = _weighted_mean_metric("loss_ratio_pct", year) or 0
    nps = _weighted_mean_metric("nps_score", year) or 0
    renewal = _weighted_mean_metric("renewal_rate_pct", year) or 0
    digital = _weighted_mean_metric("digital_adoption_pct", year) or 0

    gwp_yoy_pct = (
        ((gwp - gwp_prev) / gwp_prev * 100) if gwp_prev else 0.0
    )
    return {
        "year": year,
        "compare_to_year": prev_year,
        "gwp_eur": int(gwp),
        "gwp_yoy_pct": round(gwp_yoy_pct, 1),
        "loss_ratio_pct": round(loss_ratio, 1),
        "nps_score": int(nps),
        "renewal_rate_pct": round(renewal, 1),
        "digital_adoption_pct": round(digital, 1),
    }


def _build_pillar_inputs(year: int, prev_year: int) -> dict:
    """Per-pillar structured inputs for the yearly narrative."""
    return {
        "commercial": {
            "gwp_eur": _sum_metric("gross_written_premium_eur", year),
            "new_policies": _sum_metric("new_policies", year),
            "policies_in_force_avg":
                _weighted_mean_metric("policies_in_force", year),
            "renewal_rate_pct":
                _weighted_mean_metric("renewal_rate_pct", year),
            "gwp_yoy_pct": (
                ((_sum_metric("gross_written_premium_eur", year) or 0)
                 - (_sum_metric("gross_written_premium_eur", prev_year) or 0))
                / (_sum_metric("gross_written_premium_eur", prev_year) or 1)
                * 100
            ),
        },
        "claims": {
            "claims_reported": _sum_metric("claims_reported", year),
            "claims_paid_eur": _sum_metric("claims_paid_eur", year),
            "loss_ratio_pct":
                _weighted_mean_metric("loss_ratio_pct", year),
            "settlement_days":
                _weighted_mean_metric("avg_claim_settlement_days", year),
        },
        "customer": {
            "nps_score": _weighted_mean_metric("nps_score", year),
            "digital_adoption_pct":
                _weighted_mean_metric("digital_adoption_pct", year),
            "complaints": _sum_metric("complaints_count", year),
        },
        "compliance": {
            "fraud_cases": _sum_metric("fraud_cases_detected", year),
            "compliance_incidents":
                _sum_metric("compliance_incidents", year),
        },
    }


def _retrieve_policy_chunks(year: int) -> list[RetrievedChunk]:
    """Pull a small set of chunks the narrator can cite. Year-filtered
    via year-scoped RAG so a 2024 report doesn't quote 2020 wording."""
    try:
        return retrieve(
            "executive summary policy overview refund claims",
            k=_NARRATIVE_CHUNK_K,
            where_filter={"year": int(year)},
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("collect: chunk retrieval failed: %s", exc)
        return []


def _appendix_rows(year: int, ds: KpiDataset) -> list[dict]:
    """All monthly rows for the requested year, excluding rollups.
    The writers render this as the appendix table."""
    df = ds.df[(ds.df["year"] == year) & (~ds.df["is_rollup"])]
    return df.to_dict(orient="records")


# ---------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------


def collect(year: int) -> CollectedInputs:
    """Run every Operation + retrieval the executive report needs."""
    ds = get_dataset()
    prev_year = _previous_covered_year(year, ds)
    log.info(
        "collect: year=%d compare_to=%d csv_sha=%s...",
        year, prev_year, ds.csv_sha256[:12],
    )

    kpi_highlights = _build_kpi_highlights(year, prev_year)
    trends = _build_trends(ds)
    risk_indicators = _build_risk_indicators(year, prev_year)
    headline = _build_headline_metrics(year, prev_year)
    pillars = _build_pillar_inputs(year, prev_year)
    chunks = _retrieve_policy_chunks(year)
    appendix_rows = _appendix_rows(year, ds)

    log.info(
        "collect: %d KPIs, %d trend charts, %d risk indicators, "
        "%d narrative chunks, %d appendix rows",
        len(kpi_highlights.items),
        len(trends.charts),
        len(risk_indicators.indicators),
        len(chunks),
        len(appendix_rows),
    )

    return CollectedInputs(
        year=year,
        compare_to_year=prev_year,
        csv_sha256=ds.csv_sha256,
        kpi_highlights=kpi_highlights,
        trends=trends,
        risk_indicators=risk_indicators,
        headline_metrics=headline,
        yearly_pillar_inputs=pillars,
        policy_chunks=chunks,
        appendix_kpi_rows=appendix_rows,
    )
