"""Integration test: multi-intent query dispatches both a RAG and a data worker (Phase 11).

The Planner produces a 2-step plan (answer-policy-question + compute-kpi) and
the assembler merges both answers into a single response.

Note on intent: the question contains "gross written premium" which matches
_ANALYTICS_PATTERNS, so the intent resolver returns "analytics_or_report".
The full planner then sees the policy component too and produces a multi-step
agentic plan — intent and route can legitimately differ here.

Acceptance criteria:
  - route     == "agentic"            (multi-step plan was executed)
  - intent    == "analytics_or_report" (GWP matched the analytics patterns)
  - answer    ≥ 100 chars             (must cover both intents)
  - answer addresses refund/policy    (RAG worker was used)
  - answer addresses premium/figure   (data worker was used)
"""

import pytest


@pytest.mark.integration
def test_multi_intent_policy_and_kpi(chat) -> None:
    """One question with two intents returns an agentic route covering both."""
    resp = chat(
        "What is the refund policy in the 2024 guidelines, "
        "and what was the gross written premium in 2024?"
    )

    assert resp["route"] == "agentic", (
        f"expected route='agentic' for a multi-intent query, got {resp['route']!r}"
    )
    assert resp["intent"] == "analytics_or_report", (
        f"expected intent='analytics_or_report' (GWP in analytics patterns), "
        f"got {resp['intent']!r}"
    )
    assert len(resp["answer"]) >= 100, (
        f"multi-intent answer is too short ({len(resp['answer'])} chars); "
        "expected coverage of both the policy and the KPI intent"
    )

    answer_lower = resp["answer"].lower()
    assert "refund" in answer_lower or "policy" in answer_lower, (
        "answer must address the policy/refund intent from the RAG worker"
    )
    assert "premium" in answer_lower or any(ch.isdigit() for ch in resp["answer"]), (
        "answer must address the gross written premium intent from the data worker"
    )
