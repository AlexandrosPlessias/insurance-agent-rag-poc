"""GraphState TypedDict shared across all LangGraph nodes."""
from typing import Literal, TypedDict

from app.rag.retriever import RetrievedChunk


class ValidationResult(TypedDict, total=False):
    grounded: bool
    citations_ok: bool
    critique: str


# Phase 7: supervisor may also resolve a year-aware route. `needs_clarification`
# parks the turn and asks the user one question (e.g. "which policy year?");
# `out_of_year` is a graceful refusal when the user asks about a year the
# knowledge base doesn't cover.
Route = Literal[
    "rag",
    "report",
    "out_of_scope",
    "needs_clarification",
    "out_of_year",
    "data",
]

# Clarifier trigger reason - drives the prompt for clarifier.ask.
ClarifierReason = Literal[
    "year_missing",        # no year mentioned and history can't resolve it
    "year_gap",            # requested year falls in the KB gap (e.g. 2023)
    "ambiguous_clause",    # relevant clause differs materially across years
]


class GraphState(TypedDict, total=False):
    # --- input ---
    question: str

    # --- persistent memory (Phase 4) ---
    user_id: str
    conversation_id: int
    history: list[dict]          # last N turns of THIS conversation
    user_activity: list[dict]    # recent msgs ACROSS user's conversations

    # --- supervisor output ---
    route: Route

    # --- Phase 7: temporal + year-aware context ---
    today: str                   # ISO-8601 date (YYYY-MM-DD), injected at graph entry
    target_year: int             # year extracted/resolved from the question
    covered_years: list[int]     # mirror of settings.kb_covered_years
    clarifier_reason: ClarifierReason
    fallback_offered: list[int]  # years suggested by the out_of_year fallback
    audit_trace_id: str          # OTel trace_id (str) for audit-row correlation

    # --- rag node output ---
    reformulated_query: str
    chunks: list[RetrievedChunk]
    draft_answer: str

    # --- validator output ---
    validation: ValidationResult
    retry_count: int
    last_critique: str

    # --- Phase 8: Talk-to-Data ---
    # Operation JSON the planner LLM emitted for the current turn.
    # The UI renders it in a 'How this was computed' expander.
    data_operation: dict
    # Most recent successful Operation - the next data turn's planner
    # is fed this as drill-down context so 'now break by channel'
    # patches the prior Operation instead of restarting.
    last_data_operation: dict

    # --- terminal ---
    final_answer: str
    final_citations: list[RetrievedChunk]
    validated: bool
