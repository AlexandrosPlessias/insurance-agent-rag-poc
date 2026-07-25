"""Integration tests: Talk-to-Data routing (Phase 8).

Two tests in this file:

  test_data_scalar_grouped_drilldown — three sequential turns in ONE conversation.
    The drill-down (turn 3) inherits metric + year from turn 2, so both turns
    must share the same conversation_id.

  test_data_guards — two independent guard queries in a fresh conversation.
    Guards are self-contained and do not depend on prior turns.

Intent notes (resolver sees each query independently):
  - GWP queries match the gross_written_premium pattern → "analytics_or_report"
  - "Renewal rate", drill-down, NPS queries have no matching analytics patterns → "other"
  - The data route is set by the LLM planner, which goes beyond the regex classifier.

Acceptance criteria per turn: route == "data", answer non-empty.
"""

import pytest


@pytest.mark.integration
def test_data_scalar_grouped_drilldown(chat) -> None:
    """Scalar → grouped → drill-down (inherits context) all route to data."""
    # Turn 1 — scalar metric; GWP matches analytics patterns
    scalar = chat("What was the total gross written premium in 2024?")
    assert scalar["route"] == "data", (
        f"scalar: expected route='data', got {scalar['route']!r}"
    )
    assert scalar["intent"] == "analytics_or_report", (
        f"scalar: expected intent='analytics_or_report', got {scalar['intent']!r}"
    )
    assert len(scalar["answer"]) > 0, "scalar data answer must not be empty"

    # Turn 2 — grouped metric; resolver returns "other" (renewal rate not in patterns)
    grouped = chat("Renewal rate by channel in 2024", conversation_id=scalar["conversation_id"])
    assert grouped["route"] == "data", (
        f"grouped: expected route='data', got {grouped['route']!r}"
    )
    assert grouped["intent"] == "other", (
        f"grouped: expected intent='other' (renewal rate not in analytics patterns), "
        f"got {grouped['intent']!r}"
    )
    assert len(grouped["answer"]) > 0, "grouped data answer must not be empty"

    # Turn 3 — drill-down: same metric + year, different group_by (inherited from turn 2)
    drilldown = chat(
        "Now break that by product line instead",
        conversation_id=scalar["conversation_id"],
    )
    # "agentic" is also acceptable: the LLM may generate a multi-step plan for
    # a contextual drill-down; what matters is that it stays in analytics territory.
    assert drilldown["route"] in {"data", "agentic"}, (
        f"drill-down: expected route='data' or 'agentic', got {drilldown['route']!r}"
    )
    assert drilldown["intent"] == "other", (
        f"drill-down: expected intent='other', got {drilldown['intent']!r}"
    )
    assert len(drilldown["answer"]) > 0, "drill-down data answer must not be empty"


@pytest.mark.integration
def test_data_guards(chat) -> None:
    """Invalid-aggregation guard and year-gap guard both stay on the data route."""
    # Guard 1 — summing a stock-like metric (NPS) is semantically invalid;
    # NPS is not in _ANALYTICS_PATTERNS so intent resolves to "other"
    invalid_agg = chat("What is the total NPS summed across all channels in 2024?")
    assert invalid_agg["route"] == "data", (
        f"invalid-agg guard: expected route='data', got {invalid_agg['route']!r}"
    )
    assert invalid_agg["intent"] == "other", (
        f"invalid-agg guard: expected intent='other', got {invalid_agg['intent']!r}"
    )
    assert len(invalid_agg["answer"]) > 0, (
        "invalid-aggregation guard must return an explanatory message, not silence"
    )

    # Guard 2 — 2023 is not in the analytics DB; GWP matches analytics patterns
    year_gap = chat(
        "What was the gross written premium in 2023?",
        conversation_id=invalid_agg["conversation_id"],
    )
    assert year_gap["route"] == "data", (
        f"year-gap guard: expected route='data', got {year_gap['route']!r}"
    )
    assert year_gap["intent"] == "analytics_or_report", (
        f"year-gap guard: expected intent='analytics_or_report', got {year_gap['intent']!r}"
    )
    assert len(year_gap["answer"]) > 0, (
        "year-gap guard must return an explanatory message, not silence"
    )
