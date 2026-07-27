"""GraphState TypedDict shared across all LangGraph nodes."""

from typing import Annotated, Literal, TypedDict

from agentic_backend.config import settings
from agentic_backend.rag.retriever import RetrievedChunk

# ---------------------------------------------------------------------------
# Planner / Orchestrator data models
# ---------------------------------------------------------------------------


def _merge_step_results(current: dict | None, update: dict) -> dict:
    """Reducer: merge two step_results dicts (worker fan-out safe)."""
    return {**(current or {}), **update}


class ValidationResult(TypedDict, total=False):
    grounded: bool
    citations_ok: bool
    critique: str


# supervisor may also resolve a year-aware route. `needs_clarification`
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
    "year_missing",  # no year mentioned and history can't resolve it
    "year_gap",  # requested year falls in the KB gap (e.g. 2023)
    "ambiguous_clause",  # relevant clause differs materially across years
]


class GraphState(TypedDict, total=False):
    # --- input ---
    question: str
    response_mode: Literal["fast", "accurate"]
    planner_intent: str

    # --- persistent memory ---
    user_id: str
    conversation_id: int
    history: list[dict]  # last N turns of THIS conversation
    user_activity: list[dict]  # recent msgs ACROSS user's conversations

    # --- supervisor output ---
    route: Route

    # --- temporal + year-aware context ---
    today: str  # ISO-8601 date (YYYY-MM-DD), injected at graph entry
    target_year: int  # year extracted/resolved from the question
    covered_years: list[int]  # mirror of settings.kb_covered_years
    clarifier_reason: ClarifierReason
    fallback_offered: list[int]  # years suggested by the out_of_year fallback
    audit_trace_id: str  # OTel trace_id (str) for audit-row correlation

    # --- rag node output ---
    reformulated_query: str
    chunks: list[RetrievedChunk]
    draft_answer: str

    # --- validator output ---
    validation: ValidationResult
    retry_count: int
    last_critique: str

    # --- Talk-to-Data ---
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

    # --- Executive report metadata ---
    report_kind: str  # "executive" | "policy_summary"
    report_run_id: str  # UUID for download endpoints
    report_year: int  # year of the executive report

    # --- Planner / Orchestrator ---
    # plan: Plan serialised as a plain dict for LangGraph state compatibility.
    # step_results uses a merge-reducer so parallel workers each write their
    # own step_id key without clobbering one another.
    plan: dict
    step_results: Annotated[dict, _merge_step_results]
    partial_failure: bool
    skipped_steps: list[str]
    # current_step is worker-local: injected via Send() and never merged.
    current_step: dict


def is_fast_mode(state: GraphState) -> bool:
    """Return True if the current request should use low-latency fast mode."""
    mode = state.get("response_mode")
    if mode == "fast":
        return True
    if mode == "accurate":
        return False
    return settings.low_latency_mode
