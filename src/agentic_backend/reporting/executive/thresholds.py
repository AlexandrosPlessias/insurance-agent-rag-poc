"""deterministic risk-flag thresholds.

Severity for every risk indicator in the executive report comes from
this file. Pure-Python band lookups - no LLM is ever asked to judge
'is 0.92 amber or red?'. That's the single point of LLM-free trust
in the whole report pipeline.

Bands are inclusive at the lower bound (`>=`) and exclusive at the
upper bound (`<`). Anything off the right edge of the last band is
red by definition; off the left edge of the first band is green.

To tweak a threshold, edit the constants here - they're the only
domain dial the report has.
"""
from __future__ import annotations

from agentic_backend.reporting.executive.sections import RiskIndicator, Severity

# ---------------------------------------------------------------------
# Band constants - one tuple per indicator, in (green_max, amber_max)
# form. A value `< green_max` is green, in [green_max, amber_max) is
# amber, and >= amber_max is red.
# ---------------------------------------------------------------------

LOSS_RATIO_BANDS = (45.0, 55.0)             # %; <45 green, 45-55 amber, >=55 red
SETTLEMENT_DRIFT_BANDS = (2.0, 5.0)         # days; <2 green, 2-5 amber, >=5 red
COMPLAINTS_YOY_BANDS = (5.0, 15.0)          # %; <5 green, 5-15 amber, >=15 red
FRAUD_YOY_BANDS = (10.0, 25.0)              # %; <10 green, 10-25 amber, >=25 red
COMPLIANCE_INCIDENTS_BANDS = (1, 3)         # absolute; <1 green, 1-2 amber, >=3 red


def _band(value: float, green_max: float, amber_max: float) -> Severity:
    if value < green_max:
        return "green"
    if value < amber_max:
        return "amber"
    return "red"


# ---------------------------------------------------------------------
# Per-indicator builders. Each returns a fully-populated RiskIndicator
# (label / value_str / severity / note) ready to drop into the
# RiskIndicatorsSection.
# ---------------------------------------------------------------------


def loss_ratio_indicator(loss_ratio_pct: float) -> RiskIndicator:
    """Claims paid / GWP, as a percentage."""
    return RiskIndicator(
        label="Loss ratio",
        value_str=f"{loss_ratio_pct:.1f}%",
        severity=_band(loss_ratio_pct, *LOSS_RATIO_BANDS),
        note=(
            f"claims_paid_eur / gross_written_premium_eur. "
            f"Bands: <{LOSS_RATIO_BANDS[0]:.0f}% green, "
            f"{LOSS_RATIO_BANDS[0]:.0f}-{LOSS_RATIO_BANDS[1]:.0f}% amber, "
            f">={LOSS_RATIO_BANDS[1]:.0f}% red."
        ),
    )


def settlement_drift_indicator(drift_days: float) -> RiskIndicator:
    """YoY change in average claim settlement days (positive = slower)."""
    sign = "+" if drift_days >= 0 else "-"
    return RiskIndicator(
        label="Settlement-day drift (YoY)",
        value_str=f"{sign}{abs(drift_days):.1f} days",
        severity=_band(drift_days, *SETTLEMENT_DRIFT_BANDS),
        note=(
            f"avg_claim_settlement_days vs previous covered year. "
            f"Bands: <+{SETTLEMENT_DRIFT_BANDS[0]:.0f}d green, "
            f"+{SETTLEMENT_DRIFT_BANDS[0]:.0f}-+"
            f"{SETTLEMENT_DRIFT_BANDS[1]:.0f}d amber, "
            f">=+{SETTLEMENT_DRIFT_BANDS[1]:.0f}d red."
        ),
    )


def complaints_yoy_indicator(yoy_pct: float) -> RiskIndicator:
    """YoY % change in complaints_count."""
    sign = "+" if yoy_pct >= 0 else "-"
    return RiskIndicator(
        label="Complaints (YoY)",
        value_str=f"{sign}{abs(yoy_pct):.1f}%",
        severity=_band(yoy_pct, *COMPLAINTS_YOY_BANDS),
        note=(
            f"complaints_count YoY %. "
            f"Bands: <+{COMPLAINTS_YOY_BANDS[0]:.0f}% green, "
            f"+{COMPLAINTS_YOY_BANDS[0]:.0f}-+"
            f"{COMPLAINTS_YOY_BANDS[1]:.0f}% amber, "
            f">=+{COMPLAINTS_YOY_BANDS[1]:.0f}% red."
        ),
    )


def fraud_yoy_indicator(yoy_pct: float) -> RiskIndicator:
    """YoY % change in fraud_cases_detected."""
    sign = "+" if yoy_pct >= 0 else "-"
    return RiskIndicator(
        label="Fraud cases (YoY)",
        value_str=f"{sign}{abs(yoy_pct):.1f}%",
        severity=_band(yoy_pct, *FRAUD_YOY_BANDS),
        note=(
            f"fraud_cases_detected YoY %. "
            f"Bands: <+{FRAUD_YOY_BANDS[0]:.0f}% green, "
            f"+{FRAUD_YOY_BANDS[0]:.0f}-+"
            f"{FRAUD_YOY_BANDS[1]:.0f}% amber, "
            f">=+{FRAUD_YOY_BANDS[1]:.0f}% red."
        ),
    )


def compliance_incidents_indicator(count: int) -> RiskIndicator:
    """Absolute count of compliance_incidents for the year."""
    green_max, amber_max = COMPLIANCE_INCIDENTS_BANDS
    return RiskIndicator(
        label="Compliance incidents",
        value_str=str(count),
        severity=_band(float(count), float(green_max), float(amber_max)),
        note=(
            f"compliance_incidents sum for the year. "
            f"Bands: <{green_max} green, "
            f"{green_max}-{amber_max - 1} amber, "
            f">={amber_max} red."
        ),
    )
