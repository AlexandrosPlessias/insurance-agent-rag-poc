"""Phase 11 streaming orchestrator.

Walks the same Planner → Orchestrator → Workers → Assembler pipeline as the
compiled graph, but emits NDJSON `stage` events around each node and streams
RAG answer tokens inside the worker step.

Event types emitted:
  {"type": "stage", "node": "planner", "status": "started"|"done", "info": "…"}
  {"type": "stage", "node": "worker.step-1", "status": "started"|"done", …}
  {"type": "stage", "node": "assembler", "status": "started"|"done"}
  {"type": "token", "value": "…"}
  {"type": "meta", "reformulated_query": "…"}
  {"type": "done", "citations": […], "validated": bool, "route": "…", …}
  {"type": "error", "value": "…"}
"""
from __future__ import annotations

from typing import Iterator

import dataclasses

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.assembler_agent import assembler_node
from app.agents.planner_agent import planner_node
from app.agents.rag_agent import (
    build_rag_prompt,
    citation_payload,
    rag_node,
    reformulate_question,
)
from app.agents.validator_agent import validator_node
from app.audit import events as audit_events
from app.audit.middleware import record as audit_record
from app.graph.orchestrator import _step_state, worker_node
from app.graph.state import GraphState
from app.llm.ollama_client import get_llm
from app.observability.logging import get_logger
from app.rag.retriever import retrieve

log = get_logger(__name__)

_MAX_STEPS = 10


def _stage(node: str, status: str, info: str = "") -> dict:
    event: dict = {"type": "stage", "node": node, "status": status}
    if info:
        event["info"] = info
    return event


def _stream_rag_step(
    step: dict, state: GraphState
) -> Iterator[dict]:
    """Stream tokens for an answer-policy-question step inline."""
    args = step.get("args") or {}
    step_state = _step_state(state, args)
    question = step_state.get("question") or ""
    target_year = step_state.get("target_year")
    history = step_state.get("history") or []
    where_filter = (
        {"year": int(target_year)} if target_year is not None else None
    )

    yield _stage(f"worker.{step['step_id']}.reformulate", "started")
    reformulated = reformulate_question(question, history=history)
    step_state["reformulated_query"] = reformulated
    yield _stage(f"worker.{step['step_id']}.reformulate", "done")
    yield {"type": "meta", "reformulated_query": reformulated}

    yield _stage(f"worker.{step['step_id']}.retrieve", "started")
    chunks = retrieve(reformulated, where_filter=where_filter)
    step_state["chunks"] = chunks
    audit_record(
        step_state,
        event_type=audit_events.RAG_RETRIEVE,
        payload={
            "where": where_filter,
            "k": len(chunks),
            "reformulated_query": reformulated[:200],
            "sources": sorted({c.source for c in chunks if c.source}),
        },
    )
    yield _stage(
        f"worker.{step['step_id']}.retrieve", "done", info=f"k={len(chunks)}"
    )

    yield _stage(f"worker.{step['step_id']}.answer", "started")
    prompt = build_rag_prompt(chunks, history=history)
    from langchain_core.messages import HumanMessage, SystemMessage
    messages = [SystemMessage(content=prompt), HumanMessage(content=question)]
    parts: list[str] = []
    for piece in get_llm().stream(messages):
        text = getattr(piece, "content", "")
        if text:
            parts.append(str(text))
            yield {"type": "token", "value": str(text)}
    answer_text = "".join(parts)
    step_state["draft_answer"] = answer_text
    audit_record(
        step_state,
        event_type=audit_events.RAG_ANSWER,
        payload={
            "retry_count": 0,
            "answer_chars": len(answer_text),
            "target_year": target_year,
        },
    )
    yield _stage(
        f"worker.{step['step_id']}.answer", "done", info=f"chars={len(answer_text)}"
    )

    # Validate inline (no streaming for validator).
    step_state.update(validator_node(step_state))
    v = step_state.get("validation", {})

    # One retry if needed.
    if not (v.get("grounded") and v.get("citations_ok")):
        step_state["retry_count"] = 1
        step_state["last_critique"] = v.get("critique", "")
        yield _stage(f"worker.{step['step_id']}.answer", "started", info="retry")
        step_state.update(rag_node(step_state))
        step_state.update(validator_node(step_state))
        answer_text = step_state.get("draft_answer", answer_text)

    # Write result into step_results on the mutable state dict.
    chunks_final = step_state.get("final_citations") or step_state.get("chunks") or []
    citations = []
    for c in chunks_final:
        if isinstance(c, dict):
            citations.append(c)
        elif dataclasses.is_dataclass(c):
            citations.append(dataclasses.asdict(c))

    final_answer = step_state.get("final_answer") or answer_text
    state.setdefault("step_results", {})[step["step_id"]] = {  # type: ignore[index]
        "step_id": step["step_id"],
        "skill_name": step.get("skill_name"),
        "output": final_answer,
        "citations": citations,
        "ok": bool(step_state.get("validated", True)),
        "error": "",
        "heading": step.get("heading", "Answer"),
    }


def stream_graph(
    question: str,
    history: list[dict] | None = None,
    user_activity: list[dict] | None = None,
    user_id: str | None = None,
    conversation_id: int | None = None,
) -> Iterator[dict]:
    """Walk planner → workers → assembler, emitting NDJSON events.

    RAG steps stream tokens; all other steps run synchronously with stage
    events wrapping them.
    """
    state: GraphState = {  # type: ignore[assignment]
        "question": question,
        "retry_count": 0,
        "step_results": {},
        "history": history or [],
        "user_activity": user_activity or [],
    }
    if user_id is not None:
        state["user_id"] = user_id
    if conversation_id is not None:
        state["conversation_id"] = conversation_id

    try:
        # --- Planner ---
        yield _stage("planner", "started")
        state.update(planner_node(state))
        plan_dict = state.get("plan") or {}
        n_steps = len(plan_dict.get("steps", []))
        yield _stage("planner", "done", info=f"steps={n_steps}")

        # --- Orchestrator ---
        yield _stage("orchestrator", "started", info=f"steps={n_steps}")

        # --- Walk DAG until all steps complete ---
        steps_raw: list[dict] = plan_dict.get("steps", [])
        step_results: dict = state.get("step_results") or {}
        completed: set[str] = set(step_results.keys())
        iterations = 0

        while True:
            all_ids = {s["step_id"] for s in steps_raw}
            if completed >= all_ids or iterations >= _MAX_STEPS:
                break

            ready = [
                s for s in steps_raw
                if s["step_id"] not in completed
                and all(dep in completed for dep in s.get("depends_on", []))
            ]
            if not ready:
                break

            for step in ready:
                step_id = step["step_id"]
                skill_name = step.get("skill_name", "")
                yield _stage(f"worker.{step_id}", "started", info=f"skill={skill_name}")

                if skill_name == "answer-policy-question":
                    # Inline streaming for RAG steps.
                    yield from _stream_rag_step(step, state)
                else:
                    # Sync dispatch for non-RAG steps.
                    step_state_for_worker: GraphState = {  # type: ignore[assignment]
                        **state,
                        "current_step": step,
                    }
                    result = worker_node(step_state_for_worker)
                    step_results_update: dict = result.get("step_results", {})
                    if "step_results" not in state:
                        state["step_results"] = {}  # type: ignore[index]
                    state["step_results"].update(step_results_update)  # type: ignore[index]
                    # Emit the primary output as tokens.
                    step_result = step_results_update.get(step_id, {})
                    if step_result.get("output"):
                        yield {"type": "token", "value": step_result["output"]}

                yield _stage(f"worker.{step_id}", "done")
                completed.add(step_id)
                iterations += 1

        yield _stage("orchestrator", "done", info=f"completed={len(completed)}")

        # --- Assembler ---
        yield _stage("assembler", "started")
        assembler_result = assembler_node(state)
        state.update(assembler_result)
        yield _stage("assembler", "done")

        # Build the done event.
        citations_raw = state.get("final_citations") or []
        citations_out: list[dict] = []
        for c in citations_raw:
            if isinstance(c, dict):
                citations_out.append(c)
            elif dataclasses.is_dataclass(c):
                citations_out.append(citation_payload(c))

        yield {
            "type": "done",
            "citations": citations_out,
            "validated": bool(state.get("validated", True)),
            "retry_count": state.get("retry_count", 0),
            "critique": "",
            "route": state.get("route", "agentic"),
            "target_year": state.get("target_year"),
            "plan_id": (state.get("plan") or {}).get("plan_id"),
            "data_operation": state.get("data_operation"),
            "report_kind": state.get("report_kind"),
            "report_year": state.get("report_year"),
            "report_run_id": state.get("report_run_id"),
        }

    except Exception as exc:  # noqa: BLE001
        log.exception("stream_graph error")
        yield {"type": "error", "value": str(exc)}
