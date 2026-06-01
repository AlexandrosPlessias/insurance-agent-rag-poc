"""Clarifier node (Phase 7).

Reached when the supervisor sets route=needs_clarification. The node
emits one short clarifying question (LLM-generated, prompt-templated)
and ends the turn; the next user message re-enters the supervisor.

The graph itself does not pause waiting for the reply - clarification
is just a normal assistant message in the conversation log.
"""
from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from app.audit import events as audit_events
from app.audit.middleware import record as audit_record
from app.config import settings
from app.graph.state import GraphState
from app.llm import load_prompt
from app.llm.ollama_client import get_llm
from app.observability.logging import get_logger
from app.observability.metrics import track_node
from app.observability.tracing import annotate_request_span, get_tracer

log = get_logger(__name__)
tracer = get_tracer(__name__)

CLARIFIER_PROMPT_TEMPLATE = load_prompt("clarifier")


def _build_prompt(state: GraphState) -> str:
    today = state.get("today") or ""
    covered = state.get("covered_years") or list(settings.kb_covered_years)
    reason = state.get("clarifier_reason") or "year_missing"
    return CLARIFIER_PROMPT_TEMPLATE.format(
        today=today, covered_years=covered, reason=reason
    )


def _fallback_message(state: GraphState) -> str:
    """Deterministic clarifying question when the LLM call fails / off."""
    covered = state.get("covered_years") or list(settings.kb_covered_years)
    years_str = ", ".join(str(y) for y in covered)
    reason = state.get("clarifier_reason") or "year_missing"
    if reason == "year_missing":
        return (
            f"Which policy year are you asking about? "
            f"I have {years_str}."
        )
    if reason == "year_gap":
        target = state.get("target_year")
        return (
            f"I don't have {target} on file - I cover {years_str}. "
            f"Which of these should I use?"
        )
    # ambiguous_clause
    return (
        "Could you clarify which version of the policy you mean? "
        f"I have {years_str}."
    )


def clarifier_node(state: GraphState) -> dict:
    question = state.get("question", "")
    reason = state.get("clarifier_reason") or "year_missing"

    with tracer.start_as_current_span("clarifier.ask") as span, \
            track_node("clarifier", route="needs_clarification"):
        annotate_request_span(
            span,
            user_id=state.get("user_id"),
            conversation_id=state.get("conversation_id"),
        )
        span.set_attribute("clarifier.reason", reason)
        span.set_attribute("question.preview", question[:80])

        log.info("Clarifier asking (reason=%s)", reason)
        try:
            prompt = _build_prompt(state)
            result = get_llm().invoke(
                [
                    SystemMessage(content=prompt),
                    HumanMessage(content=question),
                ]
            )
            message = str(result.content).strip().strip('"').strip("'")
            if not message:
                raise ValueError("empty clarifier output")
        except Exception as exc:  # noqa: BLE001 - never break the turn
            log.warning(
                "Clarifier LLM failed (%s) - using fallback", exc
            )
            message = _fallback_message(state)

        audit_record(
            state,
            event_type=audit_events.CLARIFIER_ASK,
            payload={
                "reason": reason,
                "question": message,
                "original_question_preview": question[:200],
                "covered_years": state.get("covered_years"),
            },
        )

        return {
            "final_answer": message,
            "final_citations": [],
            "validated": True,
            "retry_count": 0,
        }
