"""Phase 8 executor - runs an Operation against the KPI DataFrame.

Single safety wall between the planner LLM and the data. The LLM
emits an Operation; this module is the only place that touches
pandas. Domain rules live here:

  - kind-vs-aggregation legality (sum on rates is refused, etc.)
  - 2023 year_gap (symmetric with Phase 7's RAG out_of_year)
  - unknown metric / dimension-value rejection
  - rollup rows filtered out by default to avoid double-counting

Returns an ExecutionResult dataclass that the renderer (Step 4) and
the audit/streaming layers (Step 7) consume.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from app.config import settings
from app.data.loader import KpiDataset, get_dataset
from app.data.operations import (
    AGGREGATIONS,
    Filters,
    Operation,
    OperationViolation,
)
from app.observability.logging import get_logger
from app.observability.tracing import get_tracer

log = get_logger(__name__)
tracer = get_tracer(__name__)

# Each rate / snapshot metric documents its natural weight column in
# the schema sidecar; we mirror that mapping here so the executor can
# wire up `weighted_mean` without parsing the prose description. Any
# rate / snapshot metric NOT in this dict can only be averaged with
# the unweighted `mean`.
_WEIGHTED_MEAN_WEIGHT: dict[str, str] = {
    "renewal_rate_pct":           "policies_in_force",
    "loss_ratio_pct":             "gross_written_premium_eur",
    "avg_claim_settlement_days":  "claims_reported",
    "nps_score":                  "policies_in_force",
    "digital_adoption_pct":       "new_policies",
}


@dataclass
class ExecutionResult:
    """Everything the renderer / audit layer needs after a successful run."""

    operation: Operation
    result: pd.DataFrame
    # When operation.compare_to is set, this carries the comparison
    # frame (same shape as `result`) and the executor leaves the
    # diff/ratio computation to the renderer.
    compare: pd.DataFrame | None = None
    metric: str = ""
    aggregation: str = ""
    metric_kind: str = ""
    metric_unit: str = ""
    csv_sha256: str = ""
    row_count: int = 0
    duration_s: float = 0.0
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------

def _check_metric_known(dataset: KpiDataset, metric: str) -> None:
    if metric not in dataset.metric_names():
        raise OperationViolation(
            f"Unknown metric {metric!r}. "
            f"Known: {dataset.metric_names()}",
            reason="unknown_metric",
            details={"metric": metric, "known": dataset.metric_names()},
        )


def _check_aggregation_legal(dataset: KpiDataset, op: Operation) -> None:
    allowed = dataset.valid_aggregations(op.metric)
    if op.aggregation not in allowed:
        kind = dataset.metric_kind(op.metric)
        raise OperationViolation(
            f"Aggregation {op.aggregation!r} not allowed on "
            f"{op.metric!r} (kind={kind!r}); allowed: {allowed}",
            reason="invalid_aggregation",
            details={
                "metric": op.metric,
                "metric_kind": kind,
                "requested": op.aggregation,
                "allowed": allowed,
            },
        )


def _check_year_gap(dataset: KpiDataset, filters: Filters, where: str) -> None:
    """Raise year_gap if any year in `filters.year` is in the KB gap.

    `where` describes the filter source ("filters" or "compare_to") for
    the error message so the user gets a precise pointer.
    """
    if not filters.year:
        return
    gap = set(dataset.gap_years()) & set(filters.year)
    if not gap:
        return
    raise OperationViolation(
        f"Year {sorted(gap)} is not in the dataset "
        f"({where}.year). Covered years: {dataset.covered_years()}.",
        reason="year_gap",
        details={
            "requested": sorted(gap),
            "covered": dataset.covered_years(),
            "where": where,
        },
    )


def _check_filter_domains(dataset: KpiDataset, filters: Filters, where: str) -> None:
    """Reject filter values outside the dimension's declared domain.

    Year is handled separately by `_check_year_gap`.
    """
    for dim in ("period", "channel", "product_line"):
        values = getattr(filters, dim, None)
        if not values:
            continue
        domain = set(dataset.dimension_domain(dim))
        # Period is open-ended (YYYY-MM strings), so skip the domain
        # check; the executor will surface 'empty_result' if no rows
        # match anyway.
        if dim == "period":
            continue
        unknown = [v for v in values if v not in domain]
        if unknown:
            raise OperationViolation(
                f"Unknown {dim} values in {where}: {unknown}. "
                f"Known: {sorted(domain)}",
                reason="unknown_dimension_value",
                details={
                    "where": where,
                    "dimension": dim,
                    "unknown": unknown,
                    "known": sorted(domain),
                },
            )


# ---------------------------------------------------------------------
# Filtering + aggregation
# ---------------------------------------------------------------------

def _apply_filters(df: pd.DataFrame, filters: Filters) -> pd.DataFrame:
    """Boolean-AND filter across the four dimensions."""
    out = df
    if filters.year:
        out = out[out["year"].isin(filters.year)]
    if filters.period:
        out = out[out["period"].isin(filters.period)]
    if filters.channel:
        out = out[out["channel"].isin(filters.channel)]
    if filters.product_line:
        out = out[out["product_line"].isin(filters.product_line)]
    return out


def _aggregate(
    df: pd.DataFrame,
    metric: str,
    aggregation: str,
    group_by: list[str],
) -> pd.DataFrame:
    """Run the requested aggregation. weighted_mean uses the metric's
    natural weight column from _WEIGHTED_MEAN_WEIGHT."""
    if aggregation == "count":
        # Count rows that contribute, ignoring metric values.
        if group_by:
            return df.groupby(group_by, dropna=False).size().reset_index(
                name=metric
            )
        return pd.DataFrame({metric: [len(df)]})

    if aggregation == "weighted_mean":
        weight_col = _WEIGHTED_MEAN_WEIGHT.get(metric)
        if not weight_col or weight_col not in df.columns:
            raise OperationViolation(
                f"weighted_mean has no defined weight column for "
                f"metric {metric!r}.",
                reason="invalid_aggregation",
                details={"metric": metric, "aggregation": aggregation},
            )

        def _wmean(g: pd.DataFrame) -> float:
            w = g[weight_col].astype("float64")
            v = g[metric].astype("float64")
            wsum = w.sum()
            if wsum == 0:
                return float("nan")
            return float((v * w).sum() / wsum)

        if group_by:
            out = (
                df.groupby(group_by, dropna=False)
                .apply(_wmean, include_groups=False)
                .reset_index(name=metric)
            )
            return out
        return pd.DataFrame({metric: [_wmean(df)]})

    # All other aggregations map directly to pandas reductions.
    agg_func = {
        "sum":   "sum",
        "mean":  "mean",
        "min":   "min",
        "max":   "max",
        "first": "first",
        "last":  "last",
    }[aggregation]

    if group_by:
        return (
            df.groupby(group_by, dropna=False)[metric]
            .agg(agg_func)
            .reset_index()
        )
    return pd.DataFrame({metric: [df[metric].agg(agg_func)]})


# ---------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------

def execute(
    operation: Operation,
    dataset: KpiDataset | None = None,
    *,
    include_rollups: bool = False,
) -> ExecutionResult:
    """Run an Operation and return a typed ExecutionResult.

    By default the annual-rollup rows (channel='All', product='All')
    are excluded - they're pre-aggregated convenience rows that would
    double-count if summed alongside the monthly rows. Pass
    `include_rollups=True` if the planner explicitly wants them.
    """
    dataset = dataset or get_dataset()
    t0 = time.perf_counter()

    with tracer.start_as_current_span("data.execute") as span:
        span.set_attribute("data.metric", operation.metric)
        span.set_attribute("data.aggregation", operation.aggregation)
        if operation.group_by:
            span.set_attribute(
                "data.group_by", ",".join(operation.group_by)
            )

        # --- validation ----------------------------------------------
        _check_metric_known(dataset, operation.metric)
        _check_aggregation_legal(dataset, operation)
        _check_year_gap(dataset, operation.filters, where="filters")
        _check_filter_domains(dataset, operation.filters, where="filters")
        if operation.compare_to is not None:
            _check_year_gap(
                dataset, operation.compare_to, where="compare_to"
            )
            _check_filter_domains(
                dataset, operation.compare_to, where="compare_to"
            )

        # --- main result ---------------------------------------------
        df = dataset.df
        if not include_rollups:
            df = df[~df["is_rollup"]]
        primary = _apply_filters(df, operation.filters)
        if primary.empty:
            raise OperationViolation(
                "No rows match the filters.",
                reason="empty_result",
                details={"filters": operation.filters.as_dict()},
            )
        result = _aggregate(
            primary,
            operation.metric,
            operation.aggregation,
            operation.group_by,
        )

        # Optional sort + limit.
        if operation.sort_by:
            col = operation.sort_by
            if col in result.columns:
                result = result.sort_values(col, ascending=False)
        if operation.limit:
            result = result.head(int(operation.limit))
        result = result.reset_index(drop=True)

        # --- compare_to (optional) -----------------------------------
        compare: pd.DataFrame | None = None
        if operation.compare_to is not None:
            cmp_df = _apply_filters(df, operation.compare_to)
            if cmp_df.empty:
                raise OperationViolation(
                    "No rows match the compare_to filters.",
                    reason="empty_result",
                    details={
                        "compare_to": operation.compare_to.as_dict()
                    },
                )
            compare = _aggregate(
                cmp_df,
                operation.metric,
                operation.aggregation,
                operation.group_by,
            ).reset_index(drop=True)

        elapsed = time.perf_counter() - t0
        span.set_attribute("data.row_count", len(result))
        span.set_attribute("data.duration_s", round(elapsed, 4))

        return ExecutionResult(
            operation=operation,
            result=result,
            compare=compare,
            metric=operation.metric,
            aggregation=operation.aggregation,
            metric_kind=dataset.metric_kind(operation.metric) or "",
            metric_unit=dataset.metric_unit(operation.metric),
            csv_sha256=dataset.csv_sha256,
            row_count=len(result),
            duration_s=elapsed,
        )
