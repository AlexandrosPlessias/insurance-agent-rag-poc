"""Conditional edge functions for supervisor routing + validator loop."""
from typing import Literal

from app.graph.state import GraphState
from app.observability.logging import get_logger

log = get_logger(__name__)


def route_from_supervisor(
    state: GraphState,
) -> Literal["rag", "report", "out_of_scope"]:
    return state.get("route", "rag")


def route_from_validator(state: GraphState) -> Literal["retry", "end"]:
    validation = state.get("validation", {})
    grounded = validation.get("grounded", False)
    citations_ok = validation.get("citations_ok", False)
    retry_count = state.get("retry_count", 0)

    if grounded and citations_ok:
        return "end"
    if retry_count >= 1:
        log.info(
            "Retry exhausted (count=%d) - accepting as unverified",
            retry_count,
        )
        return "end"
    log.info(
        "Validation failed (retry %d) - looping back to RAG",
        retry_count,
    )
    return "retry"
