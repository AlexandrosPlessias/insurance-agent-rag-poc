"""Integration test: planner intent is correct in both fast and accurate mode.

Verifies three things end-to-end via POST /chat:
  1. The intent resolver classifies the query correctly regardless of mode.
  2. The effective_response_mode in the response matches the requested mode
     — except when the planner overrides it (analytics/multi_intent in fast
     mode are promoted to accurate to preserve answer quality).
  3. The fast-path override fires correctly: requesting fast mode on an
     analytics query must still return effective_response_mode="accurate".

Questions are chosen to exercise all intent classifier outcomes that go
through the planner:

  policy_qa         — "What is the refund window …" (refund + year + ?)
  analytics_or_report — "What was the gross written premium …" (GWP pattern)
  other             — "How should employees handle a theft …" (no pattern match;
                      LLM planner routes it, mode is respected as-is)
"""

import pytest


@pytest.mark.integration
@pytest.mark.parametrize(
    ("question", "response_mode", "expected_intent", "expected_effective_mode"),
    [
        # policy_qa: intent unchanged in both modes; fast path taken in fast mode
        (
            "What is the refund window in the 2024 customer guidelines?",
            "fast",
            "policy_qa",
            "fast",
        ),
        (
            "What is the refund window in the 2024 customer guidelines?",
            "accurate",
            "policy_qa",
            "accurate",
        ),
        # analytics_or_report: fast mode is promoted to accurate (fast-path override)
        # This is the key correctness assertion for the planner override logic.
        (
            "What was the gross written premium in 2024?",
            "fast",
            "analytics_or_report",
            "accurate",  # override fires — fast would produce unreliable data answers
        ),
        (
            "What was the gross written premium in 2024?",
            "accurate",
            "analytics_or_report",
            "accurate",
        ),
        # other: no pattern match — LLM planner handles routing, mode respected
        (
            "How should employees handle a suspected theft incident in 2024?",
            "fast",
            "other",
            "fast",
        ),
        (
            "How should employees handle a suspected theft incident in 2024?",
            "accurate",
            "other",
            "accurate",
        ),
    ],
    ids=[
        "policy_qa/fast",
        "policy_qa/accurate",
        "analytics/fast→accurate_override",
        "analytics/accurate",
        "other/fast",
        "other/accurate",
    ],
)
def test_planner_intent_and_effective_mode(
    chat,
    question: str,
    response_mode: str,
    expected_intent: str,
    expected_effective_mode: str,
) -> None:
    """Intent and effective mode are set correctly for every classifier outcome × mode."""
    resp = chat(question, response_mode=response_mode)

    assert resp["intent"] == expected_intent, (
        f"mode={response_mode!r} question={question!r}: "
        f"expected intent={expected_intent!r}, got {resp['intent']!r}"
    )
    assert resp["effective_response_mode"] == expected_effective_mode, (
        f"mode={response_mode!r} question={question!r}: "
        f"expected effective_response_mode={expected_effective_mode!r}, "
        f"got {resp['effective_response_mode']!r}"
    )
