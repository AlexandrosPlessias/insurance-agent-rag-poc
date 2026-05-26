"""Streaming orchestrator that walks the same nodes as the compiled graph.

Mirrors `app.graph.builder` but emits `stage` events around each node
and streams tokens INSIDE the RAG node. Used by `/chat/stream`.
Accepts optional `history` and `user_activity` for Phase 4 memory.
"""
from typing import Iterator

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.rag_agent import (
    build_rag_prompt,
    citation_payload,
    reformulate_question,
)
from app.agents.report_agent import report_node
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
    history = state.get("history", [])

    if retry_count == 0:
        reformulated = reformulate_question(question, history=history)
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

    prompt = build_rag_prompt(
        chunks, critique=critique, history=history,
    )
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


def stream_graph(
    question: str,
    history: list[dict] | None = None,
    user_activity: list[dict] | None = None,
) -> Iterator[dict]:
    """Walk supervisor -> (decline | rag+validator | report)."""
    state: dict = {
        "question": question,
        "retry_count": 0,
        "history": history or [],
        "user_activity": user_activity or [],
    }

    try:
        # --- Supervisor ---
        yield _stage("supervisor", "started")
        state.update(supervisor_node(state))
        route = state["route"]
        yield _stage("supervisor", "done", info=f"route={route}")

        # --- Out-of-scope branch ---
        if route == "out_of_scope":
            state.update(decline_node(state))
            yield {"type": "token", "value": state["final_answer"]}
            yield {
                "type": "done",
                "citations": [],
                "validated": True,
                "retry_count": 0,
                "critique": "",
                "route": route,
            }
            return

        # --- Report branch ---
        if route == "report":
            yield _stage("report", "started")
            state.update(report_node(state))
            yield _stage("report", "done")
            yield {"type": "token", "value": state["final_answer"]}
            chunks_out = state.get("final_citations") or []
            yield {
                "type": "done",
                "citations": [
                    citation_payload(c) for c in chunks_out
                ],
                "validated": True,
                "retry_count": 0,
                "critique": "",
                "route": route,
            }
            return

        # --- RAG branch (with validator + 1-retry loop) ---
        yield _stage("rag", "started")
        yield from _run_rag_streaming(state)
        yield _stage("rag", "done")
        yield from _run_validator(state)

        if "final_answer" not in state:
            yield _stage("rag", "started", info="retry")
            yield from _run_rag_streaming(state)
            yield _stage("rag", "done")
            yield from _run_validator(state)

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
            "route": route,
        }
    except Exception as exc:  # noqa: BLE001
        log.exception("stream_graph error")
        yield {"type": "error", "value": str(exc)}
