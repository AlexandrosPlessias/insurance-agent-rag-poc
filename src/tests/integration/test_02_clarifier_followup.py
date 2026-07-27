"""Integration test: clarifier fires on year-ambiguous question, follow-up resolves to RAG.

Two turns share the same conversation_id so the planner stitches the bare year
token onto the original question before classification.

Acceptance criteria:
  Turn 1 — year-ambiguous, no prior history:
    - route  == "needs_clarification"
    - intent == "policy_qa"   (refund keyword + question mark identified the intent)
    - answer contains "?"     (response is a clarifying question)
  Turn 2 — bare year token "2024":
    - route     == "rag"
    - intent    == "policy_qa" (planner stitches "What is the refund window? 2024"
                                before intent classification)
    - citations ≥ 1
"""

import pytest


@pytest.mark.integration
def test_clarifier_then_rag_followup(chat) -> None:
    """Year-ambiguous question triggers the clarifier; bare-year follow-up resolves to RAG."""
    # Turn 1 — no year context: clarifier fires
    resp1 = chat("What is the refund window?")

    assert resp1["route"] == "needs_clarification", (
        f"expected route='needs_clarification', got {resp1['route']!r}"
    )
    assert resp1["intent"] == "policy_qa", (
        f"expected intent='policy_qa', got {resp1['intent']!r}"
    )
    assert "?" in resp1["answer"], (
        "clarifier response must be a question asking the user to specify a year"
    )

    # Turn 2 — pass conversation_id so the planner can stitch both turns
    resp2 = chat("2024", conversation_id=resp1["conversation_id"])

    assert resp2["route"] == "rag", (
        f"expected route='rag' after year follow-up, got {resp2['route']!r}"
    )
    assert resp2["intent"] == "policy_qa", (
        f"expected intent='policy_qa' (stitched question), got {resp2['intent']!r}"
    )
    assert len(resp2["citations"]) >= 1, (
        "RAG answer after year resolution must be grounded in at least one source"
    )
    assert len(resp2["answer"]) >= 50, "resolved RAG answer is too short to be substantive"
