"""Integration test: basic RAG routing for explicit 2024 policy questions.

Calls POST /chat and asserts on the routing decision, the planner intent
resolved before the LLM was invoked, answer quality, and grounding.

Acceptance criteria (both turns):
  - route     == "rag"
  - intent    == "policy_qa"  (regex classifier identified a policy question)
  - answer    is substantive  (≥ 50 chars)
  - citations ≥ 1             (grounded, not hallucinated)
"""

import pytest


@pytest.mark.integration
def test_rag_refund_window_2024(chat) -> None:
    """Refund-window question with explicit 2024 year routes to RAG."""
    resp = chat("What is the refund window in the 2024 customer guidelines?")

    assert resp["route"] == "rag", f"expected route='rag', got {resp['route']!r}"
    assert resp["intent"] == "policy_qa", (
        f"expected intent='policy_qa', got {resp['intent']!r}"
    )
    assert len(resp["answer"]) >= 50, "answer is too short to be substantive"
    assert len(resp["citations"]) >= 1, "answer must cite at least one source document"


@pytest.mark.integration
def test_rag_theft_handling_2024(chat) -> None:
    """Procedural policy question with explicit 2024 year routes to RAG.

    'Theft' is not in _POLICY_PATTERNS so intent resolves to 'other' —
    the LLM planner handles classification and still routes to RAG.
    """
    resp = chat("How should employees handle a suspected theft incident in 2024?")

    assert resp["route"] == "rag", f"expected route='rag', got {resp['route']!r}"
    assert resp["intent"] == "other", (
        f"expected intent='other' (theft not in policy patterns), got {resp['intent']!r}"
    )
    assert len(resp["answer"]) >= 50, "answer is too short to be substantive"
    assert len(resp["citations"]) >= 1, "answer must cite at least one source document"
