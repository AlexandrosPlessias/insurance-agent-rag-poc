"""Load the KPI CSV into a typed pandas DataFrame.

Single entry point :func:`get_dataset` caches a ``KpiDataset`` per
process so the CSV is parsed once. The result is immutable from the
caller's perspective - the executor builds new DataFrames via
``.loc``/``.groupby`` operations on the cached one.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import pandas as pd

from agentic_backend.config import settings
from agentic_backend.observability.logging import get_logger

log = get_logger(__name__)


# Columns are typed at load time so the executor doesn't have to
# re-cast. Integer columns that may contain NaN are loaded as
# nullable Int64. Column names match the real seed CSV
# (insurance_kpis_2020_2024.csv) exactly - suffixes _pct / _eur /
# _score / _count carry over from the source so the planner LLM's
# operations bind to the same names.
_DIMENSION_COLS: dict[str, str] = {
    "year": "Int64",
    "period": "string",
    "channel": "string",
    "product_line": "string",
}

_METRIC_TYPES: dict[str, str] = {
    "policies_in_force": "Int64",
    "new_policies": "Int64",
    "renewal_rate_pct": "Float64",
    "gross_written_premium_eur": "Int64",
    "claims_reported": "Int64",
    "claims_paid_eur": "Int64",
    "avg_claim_settlement_days": "Float64",
    "loss_ratio_pct": "Float64",
    "nps_score": "Int64",
    "complaints_count": "Int64",
    "fraud_cases_detected": "Int64",
    "compliance_incidents": "Int64",
    "operating_expense_eur": "Int64",
    "digital_adoption_pct": "Float64",
}

# Marker on rows where channel == 'All' AND product_line == 'All'
# (annual rollups for 2020 and 2024 only). The executor filters
# these out by default - they exist as cross-check fixtures, not
# slice-and-dice rows.
_ROLLUP_SENTINEL = "All"


@dataclass(frozen=True)
class KpiDataset:
    """Immutable wrapper around the cached DataFrame + schema."""

    df: pd.DataFrame
    schema: dict
    csv_path: Path
    schema_path: Path
    csv_sha256: str

    # ------------------------------------------------------------------
    # Convenience accessors used by the executor and the planner prompt.
    # ------------------------------------------------------------------

    def metric_names(self) -> list[str]:
        return list(self.schema["metrics"].keys())

    def metric_kind(self, metric: str) -> str | None:
        m = self.schema["metrics"].get(metric)
        return None if m is None else m["kind"]

    def metric_unit(self, metric: str) -> str:
        m = self.schema["metrics"].get(metric, {})
        return m.get("unit", "")

    def valid_aggregations(self, metric: str) -> list[str]:
        kind = self.metric_kind(metric)
        if kind is None:
            return []
        return list(self.schema["valid_aggregations"].get(kind, []))

    def dimension_domain(self, dimension: str) -> list:
        dims = self.schema["dimensions"]
        if dimension not in dims:
            return []
        if dimension == "year":
            return list(dims["year"]["covered"])
        return list(dims[dimension]["domain"])

    def covered_years(self) -> list[int]:
        return list(self.schema["dimensions"]["year"]["covered"])

    def gap_years(self) -> list[int]:
        return list(self.schema["dimensions"]["year"].get("gap", []))


def _read_csv(path: Path) -> pd.DataFrame:
    dtype_map = {**_DIMENSION_COLS, **_METRIC_TYPES}
    df = pd.read_csv(path, dtype=dtype_map)
    # Defensive: drop rows that lack a dimension key.
    df = df.dropna(subset=list(_DIMENSION_COLS.keys()))
    # Tag the annual-rollup rows so the executor can filter them out
    # by default (channel='All' AND product_line='All').
    df["is_rollup"] = (
        (df["channel"] == _ROLLUP_SENTINEL)
        & (df["product_line"] == _ROLLUP_SENTINEL)
    )
    # Stable ordering helps `weighted_mean` and `first`/`last` agg
    # produce deterministic results regardless of source row order.
    df = df.sort_values(
        ["year", "period", "channel", "product_line"]
    ).reset_index(drop=True)
    return df


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(64 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


@lru_cache(maxsize=1)
def get_dataset() -> KpiDataset:
    """Return the cached KpiDataset, loading on first call.

    The cache is process-wide and keyed on no arguments because the
    seed CSV path is config-fixed. If you need a fresh load (e.g.
    after regenerating the seed in-process), call
    ``get_dataset.cache_clear()`` first.
    """
    csv_path = settings.kpi_csv_path
    schema_path = settings.kpi_schema_path
    if not csv_path.is_file():
        raise FileNotFoundError(
            f"KPI CSV not found at {csv_path}. "
            "Generate it with `python scripts/build_kpi_seed.py`."
        )
    if not schema_path.is_file():
        raise FileNotFoundError(
            f"KPI schema not found at {schema_path}."
        )

    log.info("Loading KPI CSV: %s", csv_path)
    df = _read_csv(csv_path)
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    digest = _sha256(csv_path)
    log.info(
        "  -> %d rows, %d columns, sha256=%s...",
        len(df),
        len(df.columns),
        digest[:12],
    )
    return KpiDataset(
        df=df,
        schema=schema,
        csv_path=csv_path,
        schema_path=schema_path,
        csv_sha256=digest,
    )
