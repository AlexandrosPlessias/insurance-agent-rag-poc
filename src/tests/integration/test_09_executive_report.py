"""Integration test: executive annual report pipeline (Phase 9).

Triggers the full executive pipeline: collector → narrator → assemble →
markdown_writer. The result is a long-form Markdown document.

Intent note: "Give me the 2024 executive annual report" is an imperative
phrase with no matching policy or analytics patterns, so intent == "other".
The LLM planner routes it to report regardless.

Acceptance criteria:
  - route  == "report"
  - intent == "other"   (imperative phrase, no recognised patterns)
  - answer ≥ 500 chars  (executive reports are multi-section documents)
  - answer contains "#" (at least one Markdown header)
  - answer contains "2024"
"""

import pytest


@pytest.mark.integration
def test_executive_annual_report_2024(chat) -> None:
    """Executive annual report pipeline produces a multi-section Markdown document."""
    resp = chat("Give me the 2024 executive annual report")

    assert resp["route"] == "report", f"expected route='report', got {resp['route']!r}"
    assert resp["intent"] == "other", (
        f"expected intent='other' (imperative phrase, no recognised patterns), "
        f"got {resp['intent']!r}"
    )
    assert len(resp["answer"]) >= 500, (
        f"executive report is too short ({len(resp['answer'])} chars); "
        "expected a multi-section document (≥ 500 chars)"
    )
    assert "#" in resp["answer"], "report must contain at least one Markdown header (#)"
    assert "2024" in resp["answer"], "report must reference the requested year (2024)"
