"""Integration test: report agent produces a structured Markdown summary.

Intent note: "Give me a summary report..." does not match any analytics or
policy patterns (report was intentionally removed from _ANALYTICS_PATTERNS),
so intent resolves to "other". The LLM planner still routes it to report.

Acceptance criteria:
  - route  == "report"
  - intent == "other"   (imperative phrase, no recognised policy/analytics terms)
  - answer ≥ 200 chars  (a one-liner is not a report)
  - answer contains "#" (at least one Markdown header)
  - answer contains "2024"
"""

import pytest


@pytest.mark.integration
def test_report_summary_2024(chat) -> None:
    """Report agent returns a structured Markdown document for a 2024 summary request."""
    resp = chat("Give me a summary report of the 2024 customer guidelines")

    assert resp["route"] == "report", f"expected route='report', got {resp['route']!r}"
    assert resp["intent"] == "other", (
        f"expected intent='other' (imperative phrase, no policy/analytics keywords), "
        f"got {resp['intent']!r}"
    )
    assert len(resp["answer"]) >= 200, (
        f"report is too short ({len(resp['answer'])} chars) to be a meaningful summary"
    )
    assert "#" in resp["answer"], "report must contain at least one Markdown header (#)"
    assert "2024" in resp["answer"], "report must reference the requested year (2024)"
