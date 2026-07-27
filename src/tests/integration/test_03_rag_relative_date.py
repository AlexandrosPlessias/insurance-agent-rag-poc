"""Integration test: RAG retrieval scoped to an explicitly named historical year.

Acceptance criteria:
  - route     == "rag"
  - intent    == "policy_qa"  (refund keyword + "?" identifies a policy question)
  - answer    is substantive  (≥ 50 chars)
  - citations ≥ 1
  - a 2020 policy document appears in citations (year-scoped retrieval worked)
"""

import pytest


@pytest.mark.integration
def test_rag_2020_refund_without_receipt(chat) -> None:
    """RAG retrieves 2020-policy content when the year is explicit in the question."""
    resp = chat(
        "Based on the 2020 policy, how should a refund without "
        "a receipt but with a bank transaction be handled?"
    )

    assert resp["route"] == "rag", f"expected route='rag', got {resp['route']!r}"
    assert resp["intent"] == "policy_qa", (
        f"expected intent='policy_qa', got {resp['intent']!r}"
    )
    assert len(resp["answer"]) >= 50, "answer is too short to be substantive"
    assert len(resp["citations"]) >= 1, "answer must cite at least one source document"

    cited_sources = [c["source"] for c in resp["citations"]]
    has_2020_source = any("2020" in src for src in cited_sources)
    assert has_2020_source, (
        f"expected a 2020 policy document in citations, got: {cited_sources}"
    )
