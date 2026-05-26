"""Supervisor + decline nodes.

Phase 5: each node is wrapped in a span so the route classification
shows up in OTel traces.
"""
from langchain_core.messages import HumanMessage, SystemMessage

from app.graph.state import GraphState
from app.llm import load_prompt
from app.llm.ollama_client import get_llm
from app.observability.logging import get_logger
from app.observability.tracing import get_tracer

log = get_logger(__name__)
tracer = get_tracer(__name__)

ROUTE_PROMPT = load_prompt("supervisor")

DECLINE_MESSAGE = (
    "I'm an enterprise insurance assistant. I can answer questions "
    "about policies, coverage, claims, premiums, and exclusions based "
    "on the documents I've been given. I can't help with that "
    "request - please ask me something about your insurance documents."
)


def supervisor_node(state: GraphState) -> dict:
    question = state["question"]
    with tracer.start_as_current_span("supervisor.classify") as span:
        span.set_attribute("question.preview", question[:80])
        log.info("Supervisor classifying: %r", question[:80])
        result = get_llm().invoke(
            [
                SystemMessage(content=ROUTE_PROMPT),
                HumanMessage(content=question),
            ]
        )
        raw = str(result.content).strip().lower()
        if (
            "out_of_scope" in raw
            or "out-of-scope" in raw
            or "out of scope" in raw
        ):
            route: str = "out_of_scope"
        elif "report" in raw:
            route = "report"
        elif "rag" in raw:
            route = "rag"
        else:
            log.warning(
                "Supervisor returned unparseable %r, defaulting to rag",
                raw[:50],
            )
            route = "rag"
        span.set_attribute("supervisor.route", route)
        log.info("  -> route=%s", route)
        return {"route": route}


def decline_node(state: GraphState) -> dict:
    with tracer.start_as_current_span("decline.canned"):
        log.info("Decline node: returning canned response")
        return {
            "final_answer": DECLINE_MESSAGE,
            "final_citations": [],
            "validated": True,
            "retry_count": 0,
        }
