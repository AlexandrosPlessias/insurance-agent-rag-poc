"""Streaming orchestrator that walks the same nodes as the compiled graph.

Why a separate walker instead of `graph.stream(...)` ?
  - We want token-level streaming INSIDE the RAG node.
  - We want explicit `stage` events around each node.
LangGraph's built-in streaming modes can do both with `astream_events`,
but going async would ripple through FastAPI + httpx. For a PoC, this
manual walker is simpler and shares all node logic with the compiled
graph (see `app.graph.builder`).
"""
from typing import Iterator

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.rag_agent import (
    build_rag_prompt,
    citation_payload,
    reformulate_question,
)
from app.agents.validator_agent import validator_node
from app.graph.supervisor import decline_node, supervisor_node
from app.llm.ollama_client import get_llm
from app.observability.logging import get_logger
from app.rag.retriever import retrieve

log = get_logger(__name__)


def _stage(node: str, status: str, info: str = "") -> dict:
    event = {"type": "stage", "node": node, "status": status}
    if info:
        event["info"] = info
    return event


def _run_rag_streaming(state: dict) -> Iterator[dict]:
    """Yield token events for the RAG step. Mutates `state` in place."""
    question = state["question"]
    retry_count = state.get("retry_count", 0)
    critique = state.get("last_critique", "")

    if retry_count == 0:
        reformulated = reformulate_question(question)
        chunks = retrieve(reformulated)
        state["reformulated_query"] = reformulated
        state["chunks"] = chunks
        yield {"type": "meta", "reformulated_query": reformulated}
    else:
        log.info(
            "Streaming RAG retry %d - reusing %d chunks",
            retry_count,
            len(state.get("chunks", [])),
        )
        chunks = state.get("chunks", [])
        yield {
            "type": "token",
            "value": (
                "\n\n---\n_Retrying with validator critique: "
                f"{critique}_\n\n"
            ),
        }

    prompt = build_rag_prompt(chunks, critique=critique)
    messages = [
        SystemMessage(content=prompt),
        HumanMessage(content=question),
    ]
    parts: list[str] = []
    for piece in get_llm().stream(messages):
        text = getattr(piece, "content", "")
        if text:
            parts.append(str(text))
            yield {"type": "token", "value": str(text)}
    state["draft_answer"] = "".join(parts)


def _run_validator(state: dict) -> Iterator[dict]:
    yield _stage("validator", "started")
    state.update(validator_node(state))
    v = state.get("validation", {})
    info = (
        f"grounded={v.get('grounded')} "
        f"citations_ok={v.get('citations_ok')}"
    )
    yield _stage("validator", "done", info=info)


def stream_graph(question: str) -> Iterator[dict]:
    """Walk supervisor -> (decline | rag -> validator [-> rag -> validator])."""
    state: dict = {"question": question, "retry_count": 0}

    try:
        # --- Supervisor ---
        yield _stage("supervisor", "started")
        state.update(supervisor_node(state))
        yield _stage(
            "supervisor",
            "done",
            info=f"route={state['route']}",
        )

        # --- Out-of-scope branch ---
        if state["route"] == "out_of_scope":
            state.update(decline_node(state))
            yield {"type": "token", "value": state["final_answer"]}
            yield {
                "type": "done",
                "citations": [],
                "validated": True,
                "retry_count": 0,
                "critique": "",
            }
            return

        # --- Initial RAG attempt ---
        yield _stage("rag", "started")
        yield from _run_rag_streaming(state)
        yield _stage("rag", "done")

        # --- Validation ---
        yield from _run_validator(state)

        # --- Retry path (max 1) ---
        # validator_node sets final_answer when terminal, otherwise bumps
        # retry_count and stores last_critique.
        if "final_answer" not in state:
            yield _stage("rag", "started", info="retry")
            yield from _run_rag_streaming(state)
            yield _stage("rag", "done")
            yield from _run_validator(state)

        # --- Final event ---
        chunks = (
            state.get("final_citations")
            or state.get("chunks")
            or []
        )
        validated = bool(state.get("validated", False))
        critique = ""
        if not validated:
            critique = state.get("validation", {}).get("critique", "")
        yield {
            "type": "done",
            "citations": [citation_payload(c) for c in chunks],
            "validated": validated,
            "retry_count": state.get("retry_count", 0),
            "critique": critique,
        }
    except Exception as exc:  # noqa: BLE001
        log.exception("stream_graph error")
        yield {"type": "error", "value": str(exc)}
