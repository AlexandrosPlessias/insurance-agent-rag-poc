"""Tool: clarifier_check — check whether a question needs year clarification."""
from __future__ import annotations

import re
from dataclasses import dataclass

from agentic_backend.config import settings
from agentic_backend.tools import AgentTool


@dataclass
class ClarifierVerdict:
    needs_clarification: bool
    reason: str   # "year_missing" | "year_gap" | "" (none needed)
    extracted_year: int | None


_YEAR_RE = re.compile(r"\b(20\d{2})\b")


def _run(question: str, history_years: list[int] | None = None) -> dict:
    """Determine whether the question can proceed without clarification.

    Args:
        question: the user's raw question text.
        history_years: years extracted from recent conversation turns.

    Returns:
        ClarifierVerdict serialised as a dict.
    """
    covered = settings.kb_covered_years

    # 1. Try to extract a year from the question.
    matches = _YEAR_RE.findall(question)
    extracted: int | None = int(matches[-1]) if matches else None

    # 2. Fall back to history context.
    if extracted is None and history_years:
        extracted = history_years[-1]

    # 3. Check coverage.
    if extracted is not None and extracted not in covered:
        verdict = ClarifierVerdict(
            needs_clarification=True,
            reason="year_gap",
            extracted_year=extracted,
        )
    elif extracted is None:
        verdict = ClarifierVerdict(
            needs_clarification=True,
            reason="year_missing",
            extracted_year=None,
        )
    else:
        verdict = ClarifierVerdict(
            needs_clarification=False,
            reason="",
            extracted_year=extracted,
        )

    return {
        "needs_clarification": verdict.needs_clarification,
        "reason": verdict.reason,
        "extracted_year": verdict.extracted_year,
    }


tool = AgentTool(
    name="clarifier_check",
    description=(
        "Check whether a question requires year clarification before it can "
        "be answered. Returns a verdict with reason and extracted year."
    ),
    input_fields={
        "question": "the user's raw question text",
        "history_years": "optional list of years from recent turns",
    },
    run=_run,
)
