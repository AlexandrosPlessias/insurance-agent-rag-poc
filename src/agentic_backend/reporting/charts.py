"""Chart generation for policy reports.

Returns base64-encoded PNGs suitable for embedding in Markdown via
`![alt](data:image/png;base64,...)`.
"""
import base64
import io
import re

import matplotlib

matplotlib.use("Agg")  # non-interactive backend - required server-side
import matplotlib.pyplot as plt  # noqa: E402

from agentic_backend.observability.logging import get_logger

log = get_logger(__name__)


def _extract_amount(text) -> float | None:
    """Parse a numeric amount out of strings like 'EUR 850' or '$1,000.50'."""
    if text is None:
        return None
    cleaned = re.sub(r"[^\d.]", "", str(text))
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return None


def render_premium_chart(data: dict) -> str:
    """Bar chart comparing annual lump-sum vs total via installments.

    Returns an empty string if insufficient data.
    """
    premium = data.get("premium", {}) or {}
    if not premium:
        return ""

    annual = _extract_amount(premium.get("annual"))
    inst_amount = _extract_amount(premium.get("installment_amount"))
    inst_count = _extract_amount(premium.get("installment_count")) or 0

    labels: list[str] = []
    values: list[float] = []
    if annual:
        labels.append("Annual\n(lump sum)")
        values.append(annual)
    if inst_amount and inst_count:
        labels.append(f"Installments\n({int(inst_count)}x)")
        values.append(inst_amount * inst_count)

    if len(values) < 1:
        return ""

    fig, ax = plt.subplots(figsize=(6, 4), dpi=100)
    bars = ax.bar(labels, values, color=["#4C72B0", "#DD8452"][: len(values)])
    ax.set_ylabel("Total cost (EUR)")
    ax.set_title("Premium Payment Options")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    for bar, value in zip(bars, values):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + max(values) * 0.02,
            f"EUR {value:,.0f}",
            ha="center",
            va="bottom",
            fontsize=10,
        )

    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight")
    plt.close(fig)

    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    log.info("Premium chart rendered (%d bytes)", len(buf.getvalue()))
    return b64
