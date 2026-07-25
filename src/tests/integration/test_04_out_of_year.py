"""Integration test: out-of-year fallback when the requested year is not in the KB.

The KB covers 2020 and 2024; 2023 is a known gap that triggers the
out-of-year fallback instead of a hallucinated RAG answer.

Acceptance criteria:
  - route  == "out_of_year"
  - intent == "policy_qa"     (policy keyword + question mark)
  - answer is non-empty       (a decline message was produced, not silence)
  - answer references "2023"  (the system acknowledged the specific year)
"""

import pytest


@pytest.mark.integration
def test_out_of_year_2023_fallback(chat) -> None:
    """Querying a year not in the KB (2023) returns the out-of-year fallback route."""
    resp = chat("What does the 2023 policy say about refunds?")

    assert resp["route"] == "out_of_year", (
        f"expected route='out_of_year', got {resp['route']!r}"
    )
    assert resp["intent"] == "policy_qa", (
        f"expected intent='policy_qa', got {resp['intent']!r}"
    )
    assert len(resp["answer"]) > 0, "out-of-year response must not be empty"
    assert "2023" in resp["answer"], (
        "out-of-year response must acknowledge the specific year the user requested"
    )
