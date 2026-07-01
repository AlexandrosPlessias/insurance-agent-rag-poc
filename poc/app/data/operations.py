"""Typed Operation schema for the Phase 8 data agent.

The planner LLM emits one of these as JSON; the executor in
``app.data.executor`` consumes it. The LLM *never* writes pandas
code - this typed bridge is the single safety wall.

Design rules:
- ``metric`` must be a name declared in the schema sidecar.
- ``aggregation`` is one of the names in ``AGGREGATIONS``.
- ``filters`` and ``compare_to`` are deeply optional - the executor
  treats missing fields as "no filter on this dimension".
- ``group_by`` is a subset of the four dimension names; empty means
  a single scalar answer (one row in the result).
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

# Names match the dimension keys in insurance_kpis.schema.json.
Dimension = Literal["year", "period", "channel", "product_line"]

# Aggregations the executor knows how to run. Per-metric validity
# (e.g. sum is illegal on rate metrics) is enforced inside the
# executor against the schema sidecar - keeping it out of the type
# keeps the planner LLM unaware of constraints it'd hallucinate
# around.
AGGREGATIONS: tuple[str, ...] = (
    "sum",
    "mean",
    "weighted_mean",
    "min",
    "max",
    "first",
    "last",
    "count",
)


class Filters(BaseModel):
    """Dimension filters. None on a field = no filter on that dim."""

    year: list[int] | None = None
    period: list[str] | None = None
    channel: list[str] | None = None
    product_line: list[str] | None = None

    def is_empty(self) -> bool:
        return not any(
            v for v in (self.year, self.period, self.channel, self.product_line)
        )

    def as_dict(self) -> dict[str, list]:
        out: dict[str, list] = {}
        if self.year:
            out["year"] = list(self.year)
        if self.period:
            out["period"] = list(self.period)
        if self.channel:
            out["channel"] = list(self.channel)
        if self.product_line:
            out["product_line"] = list(self.product_line)
        return out


class Operation(BaseModel):
    """A single typed query the executor can run.

    Example::

        Operation(
            metric="renewal_rate",
            filters=Filters(year=[2024], period=["Q3"]),
            group_by=["channel"],
            aggregation="weighted_mean",
            compare_to=Filters(year=[2022], period=["Q3"]),
        )
    """

    metric: str = Field(
        ...,
        description="A metric name declared in insurance_kpis.schema.json",
        min_length=1,
    )
    filters: Filters = Field(default_factory=Filters)
    group_by: list[Dimension] = Field(default_factory=list)
    aggregation: str = Field(
        ...,
        description=(
            f"One of {AGGREGATIONS}. Per-metric legality is checked by "
            "the executor against the schema sidecar."
        ),
    )
    compare_to: Filters | None = Field(
        default=None,
        description=(
            "When set, the executor runs a second pass with these "
            "filters and joins the result alongside the primary "
            "result (year-on-year deltas, channel comparisons, etc.)."
        ),
    )
    sort_by: str | None = Field(
        default=None,
        description=(
            "Optional metric or dimension name to sort by. Direction "
            "is descending by default."
        ),
    )
    limit: int | None = Field(
        default=None,
        ge=1,
        le=200,
        description="Optional row cap on the result table.",
    )

    @field_validator("aggregation")
    @classmethod
    def _check_aggregation_known(cls, v: str) -> str:
        if v not in AGGREGATIONS:
            raise ValueError(
                f"aggregation must be one of {AGGREGATIONS}, got {v!r}"
            )
        return v

    @field_validator("group_by")
    @classmethod
    def _dedupe_group_by(cls, v: list[str]) -> list[str]:
        # Preserve order, drop duplicates the planner might emit.
        seen: set[str] = set()
        out: list[str] = []
        for item in v:
            if item not in seen:
                seen.add(item)
                out.append(item)
        return out


class OperationViolation(Exception):
    """Executor refused an Operation for a domain reason.

    The ``reason`` attribute carries a short machine-readable code:
        - "year_gap"             - target year not in kb_covered_years
        - "invalid_aggregation"  - sum on a rate, etc.
        - "unknown_metric"       - metric name not in schema sidecar
        - "unknown_dimension_value" - filter value outside the domain
        - "empty_result"         - filters/group_by produced 0 rows
    """

    def __init__(
        self,
        message: str,
        *,
        reason: str,
        details: dict | None = None,
    ):
        super().__init__(message)
        self.reason = reason
        self.details = details or {}
