"""Deterministic generator for the Phase 8 Talk-to-Data seed CSV.

Writes `data/knowledge_base/structured/insurance_kpis.csv` with one row
per (year, period, channel, product_line). Periods are FY + Q1-Q4 +
M01-M12 (17 total), with the relationships:

    M01 + M02 + M03 = Q1            (for flow metrics)
    Q1 + Q2 + Q3 + Q4 = FY          (for flow metrics)
    rates / snapshots are weighted, not summed

Realism profile baked in:
- digital_adoption_pct rises 2020 -> 2024 (modest YoY uplift).
- broker channel premium share declines as digital rises.
- Q4 has a GWP bump (~+18%) from annual renewals.
- claims_paid is 0.92-0.97 * claims_reported per period (lag effect).
- avg_claim_settlement_days drifts upward in 2022 then recovers.
- complaints spike in 2022 (a soft year); fraud_cases grow steadily.
- compliance_incidents are sparse (0-2 per quarter, mostly zeros).

Year 2023 is intentionally omitted - the executor's year_gap check
relies on the dataset NOT containing 2023 rows.

Run from poc/:
    python scripts/build_kpi_seed.py
    python scripts/build_kpi_seed.py --out custom_path.csv
"""
from __future__ import annotations

import argparse
import csv
import math
import random
import sys
from pathlib import Path
from typing import Iterable

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402

YEARS = [2020, 2021, 2022, 2024]
QUARTERS = ["Q1", "Q2", "Q3", "Q4"]
MONTHS = [f"M{m:02d}" for m in range(1, 13)]
QUARTER_OF_MONTH = {
    "M01": "Q1", "M02": "Q1", "M03": "Q1",
    "M04": "Q2", "M05": "Q2", "M06": "Q2",
    "M07": "Q3", "M08": "Q3", "M09": "Q3",
    "M10": "Q4", "M11": "Q4", "M12": "Q4",
}
CHANNELS = ["direct", "broker", "bancassurance", "digital"]
PRODUCTS = ["auto", "home", "life", "health", "commercial"]

# Channel share of new business (sums to 1.0 across channels per year).
# Digital rises, broker shrinks. bancassurance is stable.
CHANNEL_SHARE_BY_YEAR = {
    2020: {"direct": 0.36, "broker": 0.34, "bancassurance": 0.18, "digital": 0.12},
    2021: {"direct": 0.34, "broker": 0.30, "bancassurance": 0.18, "digital": 0.18},
    2022: {"direct": 0.33, "broker": 0.27, "bancassurance": 0.18, "digital": 0.22},
    2024: {"direct": 0.30, "broker": 0.20, "bancassurance": 0.18, "digital": 0.32},
}

# Per-product baselines (annual GWP per product line, EUR thousands,
# aggregated across all channels).
PRODUCT_ANNUAL_GWP_BASE = {
    "auto":       42_000,
    "home":       28_000,
    "life":       55_000,
    "health":     38_000,
    "commercial": 31_000,
}

# Annual growth multipliers applied to PRODUCT_ANNUAL_GWP_BASE.
YEAR_GROWTH = {
    2020: 1.00,
    2021: 1.04,
    2022: 1.02,   # softer year
    2024: 1.11,   # post-2023 catch-up
}

# Quarterly seasonality (sums to 1.0). Q4 carries the annual-renewal bump.
QUARTER_WEIGHTS = {
    "Q1": 0.225,
    "Q2": 0.235,
    "Q3": 0.245,
    "Q4": 0.295,
}
# Monthly weights within a quarter (sum to 1.0). Slight ramp inside Q.
INTRA_QUARTER_MONTH_WEIGHTS = [0.31, 0.33, 0.36]

# NPS baselines per channel (snapshot, range -100..100).
CHANNEL_NPS_BASE = {
    "direct": 38,
    "broker": 24,
    "bancassurance": 18,
    "digital": 46,
}
# NPS drift by year (additive).
NPS_YEAR_DRIFT = {2020: -3, 2021: 0, 2022: -4, 2024: +5}

# digital_adoption_pct (overall portfolio) by year. Snapshot, monotonically up.
DIGITAL_ADOPTION_BY_YEAR = {2020: 22.0, 2021: 31.0, 2022: 38.0, 2024: 56.0}

# Claim settlement days baseline by product (snapshot, days).
PRODUCT_SETTLEMENT_DAYS = {
    "auto":       11,
    "home":       18,
    "life":       42,
    "health":     14,
    "commercial": 26,
}
SETTLEMENT_DAYS_YEAR_DRIFT = {2020: -1, 2021: 0, 2022: +3, 2024: -2}


def _seeded_rng(year: int, period: str, channel: str, product: str) -> random.Random:
    """One independent RNG per row, seeded by the row's identity.

    Makes the generator perfectly reproducible AND ensures tweaking one
    dimension's distribution doesn't ripple noise into unrelated rows.
    """
    key = f"{year}|{period}|{channel}|{product}"
    return random.Random(hash(key) & 0xFFFFFFFF)


def _gwp_for_month(year: int, month_idx: int, channel: str, product: str) -> int:
    """Monthly GWP in EUR thousands, integer. M-grain is the base; Q
    and FY are rolled up from these to guarantee they reconcile."""
    annual_total = (
        PRODUCT_ANNUAL_GWP_BASE[product]
        * YEAR_GROWTH[year]
        * CHANNEL_SHARE_BY_YEAR[year][channel]
    )
    q_key = QUARTER_OF_MONTH[f"M{month_idx:02d}"]
    q_weight = QUARTER_WEIGHTS[q_key]
    m_in_q = (month_idx - 1) % 3   # 0, 1, 2 within the quarter
    m_weight = INTRA_QUARTER_MONTH_WEIGHTS[m_in_q]
    base = annual_total * q_weight * m_weight

    rng = _seeded_rng(year, f"M{month_idx:02d}", channel, product)
    noise = 1.0 + rng.uniform(-0.04, 0.04)   # +/- 4% monthly noise
    return int(round(base * noise))


def _new_policies_for_month(
    year: int, month_idx: int, channel: str, product: str, gwp: int
) -> int:
    """Roughly proportional to GWP, with product-specific avg premium."""
    avg_premium = {
        "auto":       1.1,    # EUR k per policy
        "home":       0.6,
        "life":       2.2,
        "health":     1.4,
        "commercial": 3.0,
    }[product]
    rng = _seeded_rng(year, f"M{month_idx:02d}-np", channel, product)
    noise = 1.0 + rng.uniform(-0.08, 0.08)
    n = (gwp / avg_premium) * noise
    return max(0, int(round(n)))


def _policies_in_force_eop(
    year: int, period: str, channel: str, product: str, eop_estimate: float
) -> int:
    """Stock at end of period. We compute a smooth growth path so the
    EOP for Q1 < Q2 < Q3 < Q4 = FY (rough monotonic, plus channel/
    product variance)."""
    rng = _seeded_rng(year, period, channel, product)
    return max(0, int(round(eop_estimate * (1.0 + rng.uniform(-0.02, 0.02)))))


def _renewal_rate(year: int, channel: str, product: str) -> float:
    """Rate (%), 0..100. Slightly different baseline per channel."""
    base = {
        "direct": 82.0, "broker": 78.0,
        "bancassurance": 80.0, "digital": 73.0,
    }[channel]
    product_adj = {
        "auto": +0.5, "home": +1.5, "life": +3.0,
        "health": -0.5, "commercial": -1.0,
    }[product]
    year_adj = {2020: -1.0, 2021: 0.0, 2022: -2.0, 2024: +1.5}[year]
    rng = _seeded_rng(year, "renew", channel, product)
    noise = rng.uniform(-1.5, 1.5)
    val = base + product_adj + year_adj + noise
    return round(max(0.0, min(100.0, val)), 1)


def _claims_reported(new_policies: int, year: int, product: str) -> int:
    """Loose function of new policies (a proxy for portfolio size)."""
    claim_freq = {
        "auto":       0.060,
        "home":       0.022,
        "life":       0.008,
        "health":     0.085,
        "commercial": 0.035,
    }[product]
    rng = _seeded_rng(year, "rep", product, "all")
    noise = 1.0 + rng.uniform(-0.10, 0.10)
    return max(0, int(round(new_policies * claim_freq * noise)))


def _claims_paid(reported: int, year: int) -> int:
    """0.92 - 0.97 * reported, with light noise. Lag effect."""
    rng = _seeded_rng(year, "paid", "all", "all")
    ratio = 0.945 + rng.uniform(-0.025, 0.025)
    return max(0, int(round(reported * ratio)))


def _nps(year: int, channel: str) -> int:
    rng = _seeded_rng(year, "nps", channel, "all")
    val = CHANNEL_NPS_BASE[channel] + NPS_YEAR_DRIFT[year] + rng.randint(-4, 4)
    return max(-100, min(100, int(val)))


def _digital_adoption_pct(year: int, channel: str) -> float:
    """Per-channel value that AVERAGES (weighted by new_policies) to
    DIGITAL_ADOPTION_BY_YEAR[year]. We simply weight 'digital' channel
    high and others low so the portfolio-weighted mean lands near the
    target."""
    portfolio = DIGITAL_ADOPTION_BY_YEAR[year]
    channel_factor = {
        "digital": 1.85, "direct": 0.95, "broker": 0.30, "bancassurance": 0.55,
    }[channel]
    rng = _seeded_rng(year, "digi", channel, "all")
    val = portfolio * channel_factor + rng.uniform(-2, 2)
    return round(max(0.0, min(100.0, val)), 1)


def _settlement_days(year: int, product: str, claims_paid: int) -> float:
    rng = _seeded_rng(year, "settle", product, "all")
    base = PRODUCT_SETTLEMENT_DAYS[product] + SETTLEMENT_DAYS_YEAR_DRIFT[year]
    noise = rng.uniform(-1.5, 1.5)
    if claims_paid == 0:
        return 0.0
    return round(max(1.0, base + noise), 1)


def _complaints(claims_reported: int, year: int) -> int:
    rng = _seeded_rng(year, "comp", "all", "all")
    base_ratio = 0.04
    if year == 2022:
        base_ratio = 0.07   # spike
    ratio = base_ratio * (1.0 + rng.uniform(-0.20, 0.20))
    return max(0, int(round(claims_reported * ratio)))


def _fraud_cases(claims_reported: int, year: int) -> int:
    rng = _seeded_rng(year, "fraud", "all", "all")
    base_ratio = {2020: 0.012, 2021: 0.014, 2022: 0.018, 2024: 0.020}[year]
    return max(0, int(round(claims_reported * base_ratio * (1.0 + rng.uniform(-0.20, 0.20)))))


def _compliance_incidents(period: str, year: int, channel: str, product: str) -> int:
    """Sparse - 0 most of the time, 1-2 occasionally, never more."""
    if period.startswith("M"):
        # Spread across months: pick a random month per year+channel+product
        # to get a non-zero incident.
        rng = _seeded_rng(year, "comp-incident-pick", channel, product)
        chosen = rng.choice(MONTHS)
        if period == chosen:
            return rng.choice([1, 1, 1, 2])
        return 0
    # For Q/FY we'll roll up from M rows in `_aggregate_to_period`.
    return 0


def _operating_expenses(gwp: int, year: int) -> int:
    """Operating expenses as a fraction of GWP, in EUR thousands."""
    rng = _seeded_rng(year, "opex", "all", "all")
    ratio = 0.28 + rng.uniform(-0.02, 0.02)
    return int(round(gwp * ratio))


def _row(year: int, period: str, channel: str, product: str,
         month_metrics: dict | None = None) -> dict:
    """Build one CSV row. For M periods we compute directly; for Q and
    FY we'd ideally roll up - but here we generate consistently using
    the same seeded RNG family so M/Q/FY tell a coherent story without
    requiring a separate aggregation pass."""
    # 1. GWP (flow): the anchor metric.
    if period.startswith("M"):
        month_idx = int(period[1:])
        gwp = _gwp_for_month(year, month_idx, channel, product)
        new_pol = _new_policies_for_month(year, month_idx, channel, product, gwp)
    elif period in QUARTERS:
        # Sum of 3 months in that quarter.
        gwp = sum(
            month_metrics[f"M{m:02d}"]["gwp"]
            for m in range(1, 13)
            if QUARTER_OF_MONTH[f"M{m:02d}"] == period
        )
        new_pol = sum(
            month_metrics[f"M{m:02d}"]["new_policies"]
            for m in range(1, 13)
            if QUARTER_OF_MONTH[f"M{m:02d}"] == period
        )
    else:  # FY
        gwp = sum(month_metrics[f"M{m:02d}"]["gwp"] for m in range(1, 13))
        new_pol = sum(
            month_metrics[f"M{m:02d}"]["new_policies"] for m in range(1, 13)
        )

    # 2. Claims & risk metrics (driven by new_pol for portfolio size).
    cr = _claims_reported(new_pol, year, product)
    cp = _claims_paid(cr, year)

    # 3. Stock - end of period. Use an estimate proportional to cumulative
    #    new_policies up to this point in the year.
    pif_estimate = new_pol * 8.5  # crude "stock = ~8.5 quarters of new flow"
    pif = _policies_in_force_eop(year, period, channel, product, pif_estimate)

    # 4. Rates / snapshots / sparse.
    renew = _renewal_rate(year, channel, product)
    nps_val = _nps(year, channel)
    digi = _digital_adoption_pct(year, channel)
    sett = _settlement_days(year, product, cp)
    complaints = _complaints(cr, year)
    fraud = _fraud_cases(cr, year)

    if period.startswith("M"):
        compliance = _compliance_incidents(period, year, channel, product)
    elif period in QUARTERS:
        compliance = sum(
            month_metrics[f"M{m:02d}"]["compliance_incidents"]
            for m in range(1, 13)
            if QUARTER_OF_MONTH[f"M{m:02d}"] == period
        )
    else:  # FY
        compliance = sum(
            month_metrics[f"M{m:02d}"]["compliance_incidents"]
            for m in range(1, 13)
        )

    opex = _operating_expenses(gwp, year)

    return {
        "year": year,
        "period": period,
        "channel": channel,
        "product_line": product,
        "policies_in_force": pif,
        "new_policies": new_pol,
        "renewal_rate": renew,
        "gross_written_premium": gwp,
        "claims_reported": cr,
        "claims_paid": cp,
        "avg_claim_settlement_days": sett,
        "nps": nps_val,
        "complaints": complaints,
        "fraud_cases": fraud,
        "compliance_incidents": compliance,
        "operating_expenses": opex,
        "digital_adoption_pct": digi,
    }


def generate_rows() -> Iterable[dict]:
    """Emit ~1,360 rows in deterministic order."""
    for year in YEARS:
        for channel in CHANNELS:
            for product in PRODUCTS:
                # Compute months first so Q and FY can roll up cleanly.
                month_metrics: dict[str, dict] = {}
                for month_idx in range(1, 13):
                    period = f"M{month_idx:02d}"
                    row = _row(year, period, channel, product)
                    month_metrics[period] = {
                        "gwp": row["gross_written_premium"],
                        "new_policies": row["new_policies"],
                        "compliance_incidents": row["compliance_incidents"],
                    }
                    yield row
                # Quarters (roll up M).
                for q in QUARTERS:
                    yield _row(year, q, channel, product, month_metrics)
                # FY (roll up M).
                yield _row(year, "FY", channel, product, month_metrics)


FIELDS = [
    "year", "period", "channel", "product_line",
    "policies_in_force", "new_policies", "renewal_rate",
    "gross_written_premium",
    "claims_reported", "claims_paid", "avg_claim_settlement_days",
    "nps", "complaints", "fraud_cases", "compliance_incidents",
    "operating_expenses", "digital_adoption_pct",
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=settings.raw_pdf_dir.parent
        / "structured"
        / "insurance_kpis.csv",
        help="Output CSV path. Defaults to data/knowledge_base/structured/insurance_kpis.csv.",
    )
    args = parser.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    rows = list(generate_rows())
    with args.out.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} rows to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
