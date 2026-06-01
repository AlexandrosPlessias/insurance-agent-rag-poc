"""Supervisor + decline + out-of-year fallback nodes.

Phase 7 changes:
- Inject today's ISO date and the KB-covered-years list into state at
  graph entry, so downstream nodes (and any future LLM call) can resolve
  relative dates and scope retrieval.
- Extract `target_year` deterministically from the question (regex first;
  history fallback) before calling the supervisor LLM.
- Apply two deterministic overrides after classification:
    * target_year set but not in covered_years -> route=out_of_year
    * route=rag and no year resolvable        -> route=needs_clarification
- Write a `supervisor.route` audit event on every classification.
- New `fallback_node` returns a templated reply naming the nearest covered
  years; new `clarifier` node lives in app.graph.clarifier.
"""
from __future__ import annotations

import re
from datetime import date

from langchain_core.messages import HumanMessage, SystemMessage

from app.audit import events as audit_events
from app.audit.middleware import current_trace_id, record as audit_record
from app.config import settings
from app.graph.state import GraphState
from app.llm import load_prompt
from app.llm.ollama_client import get_llm
from app.observability.logging import get_logger
from app.observability.metrics import track_node
from app.observability.tracing import annotate_request_span, get_tracer

log = get_logger(__name__)
tracer = get_tracer(__name__)

ROUTE_PROMPT_TEMPLATE = load_prompt("supervisor")

DECLINE_MESSAGE = (
    "I'm an enterprise insurance assistant. I can answer questions "
    "about policies, coverage, claims, premiums, and exclusions based "
    "on the documents I've been given. I can't help with that "
    "request - please ask me something about your insurance documents."
)

# Year-extraction regex. Matches any 20xx token in the user's question.
# Good enough for the PoC; an LLM extractor is worth piloting only if
# we see real cases the regex misses.
_YEAR_RE = re.compile(r"\b(20\d\d)\b")

# How far back to scan history when the current question doesn't mention
# a year. The Phase 4 memory loader caps history at ~6 messages anyway.
_HISTORY_LOOKBACK = 6


def _extract_year(text: str) -> int | None:
    matches = _YEAR_RE.findall(text or "")
    if not matches:
        return None
    # When the user lists several years, prefer the last one - usually
    # the one they latched onto in the trailing clause.
    return int(matches[-1])


def _resolve_year_from_history(history: list[dict]) -> int | None:
    """Walk recent history newest-first; return the most recent year."""
    if not history:
        return None
    for msg in reversed(history[-_HISTORY_LOOKBACK:]):
        year = _extract_year(str(msg.get("content", "")))
        if year is not None:
            return year
    return None


def _last_assistant_was_clarifier(history: list[dict]) -> bool:
    """True if the immediately-prior assistant turn was a clarifier.

    `history` is loaded BEFORE the current user message is persisted
    (see api.routes.chat._load_memory), so the most recent assistant
    entry in it is the turn that triggered the user's reply.
    """
    for msg in reversed(history):
        role = msg.get("role")
        if role == "assistant":
            return msg.get("route") == "needs_clarification"
        if role == "user":
            return False
    return False


def _last_user_question(history: list[dict]) -> str | None:
    """The most recent prior user message - the question the clarifier
    was answering on behalf of. Skips assistant + system rows."""
    for msg in reversed(history):
        if msg.get("role") == "user":
            content = (msg.get("content") or "").strip()
            return content or None
    return None


def _nearest_covered(target: int, covered: list[int]) -> list[int]:
    """Return up to 2 nearest covered years (one below, one above)."""
    below = [y for y in covered if y < target]
    above = [y for y in covered if y > target]
    nearest: list[int] = []
    if below:
        nearest.append(max(below))
    if above:
        nearest.append(min(above))
    return nearest or list(covered)


def _classify_with_llm(question: str, today: str, covered: list[int]) -> str:
    prompt = ROUTE_PROMPT_TEMPLATE.format(
        today=today, covered_years=covered
    )
    result = get_llm().invoke(
        [
            SystemMessage(content=prompt),
            HumanMessage(content=question),
        ]
    )
    raw = str(result.content).strip().lower()
    # Order matters - check the more specific tokens first so 'data'
    # doesn't accidentally swallow 'database' or similar, and so the
    # ambiguous 'rag' word (which is also a substring of many things)
    # only fires as a last resort.
    if (
        "out_of_scope" in raw
        or "out-of-scope" in raw
        or "out of scope" in raw
    ):
        return "out_of_scope"
    if "report" in raw:
        return "report"
    if "data" in raw:
        return "data"
    if "rag" in raw:
        return "rag"
    log.warning(
        "Supervisor returned unparseable %r, defaulting to rag",
        raw[:50],
    )
    return "rag"


def supervisor_node(state: GraphState) -> dict:
    question = state.get("question") or ""
    history = state.get("history") or []
    today = state.get("today") or date.today().isoformat()
    covered = list(state.get("covered_years") or settings.kb_covered_years)
    trace_id = state.get("audit_trace_id") or current_trace_id()

    # Phase 7 - clarifier follow-up: if the immediately-prior assistant
    # turn was the clarifier, the current user message is supplying the
    # missing piece (typically just a year, e.g. "2024"). Stitch the
    # original question back in so downstream classification and
    # retrieval see the full intent. Without this, "2024" alone gets
    # classified as out_of_scope and the assistant loops.
    is_clarifier_followup = _last_assistant_was_clarifier(history)
    original_question = (
        _last_user_question(history) if is_clarifier_followup else None
    )
    if is_clarifier_followup and original_question:
        effective_question = f"{original_question} {question}".strip()
        log.info(
            "Supervisor: clarifier follow-up detected, combining "
            "original=%r + new=%r",
            original_question[:80],
            question[:80],
        )
    else:
        effective_question = question

    with tracer.start_as_current_span("supervisor.classify") as span, \
            track_node("supervisor"):
        annotate_request_span(
            span,
            user_id=state.get("user_id"),
            conversation_id=state.get("conversation_id"),
        )
        span.set_attribute("question.preview", effective_question[:80])
        span.set_attribute("supervisor.today", today)
        span.set_attribute("supervisor.covered_years", str(covered))
        if is_clarifier_followup:
            span.set_attribute("supervisor.clarifier_followup", True)

        # 1. Deterministic year extraction (effective question first,
        #    then history). The follow-up reply is part of the
        #    effective question, so a bare "2024" still resolves.
        explicit_year = _extract_year(effective_question)
        target_year = explicit_year or _resolve_year_from_history(history)
        if target_year is not None:
            span.set_attribute("supervisor.target_year", target_year)
            span.set_attribute(
                "supervisor.year_source",
                "question" if explicit_year else "history",
            )

        update: dict = {
            "today": today,
            "covered_years": covered,
            "audit_trace_id": trace_id or "",
        }
        # Rewrite question so RAG retrieves on the original intent,
        # not on the bare follow-up token.
        if is_clarifier_followup and original_question:
            update["question"] = effective_question
        if target_year is not None:
            update["target_year"] = target_year

        # 2. Out-of-year short-circuit (no LLM call needed).
        if target_year is not None and target_year not in covered:
            fallback = _nearest_covered(target_year, covered)
            update["route"] = "out_of_year"
            update["fallback_offered"] = fallback
            span.set_attribute("supervisor.route", "out_of_year")
            log.info(
                "  -> out_of_year (target=%d, offering=%s)",
                target_year,
                fallback,
            )
            audit_record(
                {**state, **update},
                event_type=audit_events.SUPERVISOR_ROUTE,
                payload={
                    "route": "out_of_year",
                    "target_year": target_year,
                    "covered_years": covered,
                    "resolved_today": today,
                },
            )
            return update

        # 3. LLM classification (rag / report / out_of_scope) on the
        #    effective question (clarifier follow-up already stitched in).
        log.info("Supervisor classifying: %r", effective_question[:80])
        route = _classify_with_llm(effective_question, today, covered)

        # 4. Needs-clarification override: a RAG question with no resolvable
        #    year is exactly the case Phase 7 was asked to handle.
        clarifier_reason = None
        if route == "rag" and target_year is None:
            route = "needs_clarification"
            clarifier_reason = "year_missing"
            log.info("  -> escalating to needs_clarification (year missing)")

        update["route"] = route
        if clarifier_reason:
            update["clarifier_reason"] = clarifier_reason
        span.set_attribute("supervisor.route", route)
        log.info("  -> route=%s", route)

        audit_record(
            {**state, **update},
            event_type=audit_events.SUPERVISOR_ROUTE,
            payload={
                "route": route,
                "target_year": target_year,
                "covered_years": covered,
                "resolved_today": today,
                "clarifier_reason": clarifier_reason,
            },
        )
        return update


def decline_node(state: GraphState) -> dict:
    with tracer.start_as_current_span("decline.canned") as span, \
            track_node("decline", route="out_of_scope"):
        annotate_request_span(
            span,
            user_id=state.get("user_id"),
            conversation_id=state.get("conversation_id"),
        )
        log.info("Decline node: returning canned response")
        audit_record(
            state,
            event_type=audit_events.DECLINE,
            payload={"reason": "out_of_scope"},
        )
        return {
            "final_answer": DECLINE_MESSAGE,
            "final_citations": [],
            "validated": True,
            "retry_count": 0,
        }


def fallback_node(state: GraphState) -> dict:
    """Out-of-year fallback. Reached only via supervisor route=out_of_year."""
    target_year = state.get("target_year")
    offered = state.get("fallback_offered") or list(
        state.get("covered_years") or settings.kb_covered_years
    )
    with tracer.start_as_current_span("fallback.out_of_year") as span, \
            track_node("fallback", route="out_of_year"):
        annotate_request_span(
            span,
            user_id=state.get("user_id"),
            conversation_id=state.get("conversation_id"),
        )
        span.set_attribute("fallback.target_year", target_year or -1)
        span.set_attribute("fallback.offered", str(offered))
        log.info(
            "Year fallback: target=%s offering=%s", target_year, offered
        )

        offered_str = " or ".join(str(y) for y in offered) if offered else "?"
        covered = ", ".join(
            str(y) for y in (state.get("covered_years") or [])
        )
        message = (
            f"I don't have policy documents for {target_year}. "
            f"My knowledge base covers {covered}. "
            f"Would you like me to answer using {offered_str} instead?"
        )

        audit_record(
            state,
            event_type=audit_events.YEAR_FALLBACK,
            payload={
                "requested": target_year,
                "offered": offered,
                "covered_years": state.get("covered_years"),
            },
        )

        return {
            "final_answer": message,
            "final_citations": [],
            "validated": True,
            "retry_count": 0,
        }
