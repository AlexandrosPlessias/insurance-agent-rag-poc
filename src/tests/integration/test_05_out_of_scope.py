"""Integration test: out-of-scope decline for questions unrelated to insurance policy.

Acceptance criteria:
  - route  == "out_of_scope"
  - intent == "other"          (no policy or analytics keywords)
  - answer is non-empty        (a polite decline was produced)
  - answer.strip() != "4"      (system declined rather than answered the math)
"""

import pytest


@pytest.mark.integration
def test_out_of_scope_math_question(chat) -> None:
    """A non-insurance question is declined with the out-of-scope route."""
    resp = chat("What is 2 + 2?")

    assert resp["route"] == "out_of_scope", (
        f"expected route='out_of_scope', got {resp['route']!r}"
    )
    assert resp["intent"] == "other", (
        f"expected intent='other' (no insurance keywords), got {resp['intent']!r}"
    )
    assert len(resp["answer"]) > 0, "out-of-scope response must not be empty"
    assert resp["answer"].strip() != "4", (
        "system must decline the out-of-scope question, not answer it"
    )
