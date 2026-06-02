"""Streaming orchestrator that walks the same nodes as the compiled graph.

Mirrors `app.graph.builder` but emits `stage` events around each node
and streams tokens INSIDE the RAG node. Used by `/chat/stream`.
Accepts optional `history` and `user_activity` for Phase 4 memory.

Phase 7: forwards `target_year` to retrieval as `where_filter`, and
handles the two new supervisor routes (`needs_clarification` and
`out_of_year`) as terminal branches similar to `out_of_scope`.
"""
from typing import Iterator

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.data_agent import (
    _refusal_message as data_refusal_message,
    plan_query as data_plan_query,
    render as data_render,
)
from app.agents.rag_agent import (
    build_rag_prompt,
    citation_payload,
    reformulate_question,
)
from app.agents.report_agent import report_node
from app.agents.validator_agent import validator_node
from app.audit import events as audit_events
from app.audit.middleware import record as audit_record
from app.data import (
    OperationViolation,
    execute as data_execute,
    get_dataset,
)
from app.graph.clarifier import clarifier_node
from app.graph.state import GraphState
from app.graph.supervisor import (
    decline_node,
    fallback_node,
    supervisor_node,
)
from app.llm.ollama_client import get_llm
from app.observability.logging import get_logger
from app.rag.retriever import retrieve

log = get_logger(__name__)


def _stage(node: str, status: str, info: str = "") -> dict:
    event = {"type": "stage", "node": node, "status": status}
    if info:
        event["info"] = info
    return event


def _run_rag_streaming(state: GraphState) -> Iterator[dict]:
    """Yield token events for the RAG step. Mutates `state` in place."""
    question = state.get("question") or ""
    retry_count = state.get("retry_count", 0)
    critique = state.get("last_critique", "")
    history = state.get("history", [])
    target_year = state.get("target_year")
    where_filter = (
        {"year": int(target_year)} if target_year is not None else None
    )

    # Phase 7 follow-up: emit per-substage events so the UI can light
    # up the three RAG sub-pills (reformulate / retrieve / answer)
    # independently. On retry, reformulate + retrieve are skipped
    # (chunks reused); their pills stay in whatever state they ended
    # the first pass.
    if retry_count == 0:
        yield _stage("rag.reformulate", "started")
        reformulated = reformulate_question(question, history=history)
        state["reformulated_query"] = reformulated
        yield _stage("rag.reformulate", "done")

        yield _stage("rag.retrieve", "started")
        chunks = retrieve(reformulated, where_filter=where_filter)
        state["chunks"] = chunks
        audit_record(
            state,
            event_type=audit_events.RAG_RETRIEVE,
            payload={
                "where": where_filter,
                "k": len(chunks),
                "reformulated_query": reformulated[:200],
                "sources": sorted({c.source for c in chunks if c.source}),
            },
        )
        yield _stage("rag.retrieve", "done", info=f"k={len(chunks)}")
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

    yield _stage("rag.answer", "started")
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
    answer_text = "".join(parts)
    state["draft_answer"] = answer_text
    audit_record(
        state,
        event_type=audit_events.RAG_ANSWER,
        payload={
            "retry_count": retry_count,
            "answer_chars": len(answer_text),
            "target_year": target_year,
        },
    )
    yield _stage(
        "rag.answer", "done", info=f"chars={len(answer_text)}"
    )


def _run_validator(state: GraphState) -> Iterator[dict]:
    yield _stage("validator", "started")
    state.update(validator_node(state))
    v = state.get("validation", {})
    info = (
        f"grounded={v.get('grounded')} "
        f"citations_ok={v.get('citations_ok')}"
    )
    yield _stage("validator", "done", info=info)


def _run_data_streaming(state: GraphState) -> Iterator[dict]:
    """Phase 8 - emit per-substage events for the data branch.

    plan + execute fire as their own sub-pills so the UI stepper
    lights them up independently, mirroring the rag.reformulate /
    rag.retrieve / rag.answer pattern. Audit rows are written for
    both data.plan and data.execute so the streaming and compiled-
    graph paths produce the same audit trail.
    """
    from datetime import date

    question = state.get("question") or ""
    today = state.get("today") or date.today().isoformat()
    previous_op = state.get("last_data_operation")
    ds = get_dataset()

    # --- plan ----------------------------------------------------
    yield _stage("data.plan", "started")
    try:
        op = data_plan_query(question, today, previous_operation=previous_op)
    except OperationViolation as exc:
        audit_record(
            state,
            event_type=audit_events.DATA_PLAN,
            payload={
                "ok": False,
                "reason": exc.reason,
                "drilldown": bool(previous_op),
            },
        )
        yield _stage(
            "data.plan", "done", info=f"refused:{exc.reason}"
        )
        msg = data_refusal_message(exc, ds.covered_years())
        state["final_answer"] = msg
        yield {"type": "token", "value": msg}
        return
    audit_record(
        state,
        event_type=audit_events.DATA_PLAN,
        payload={
            "ok": True,
            "operation": op.model_dump(mode="json"),
            "drilldown": bool(previous_op),
        },
    )
    yield _stage(
        "data.plan",
        "done",
        info=f"metric={op.metric} agg={op.aggregation}",
    )

    # --- execute -------------------------------------------------
    yield _stage("data.execute", "started")
    try:
        result = data_execute(op, dataset=ds)
    except OperationViolation as exc:
        audit_record(
            state,
            event_type=audit_events.DATA_EXECUTE,
            payload={
                "ok": False,
                "reason": exc.reason,
                "operation": op.model_dump(mode="json"),
                "csv_sha256": ds.csv_sha256,
            },
        )
        yield _stage(
            "data.execute", "done", info=f"refused:{exc.reason}"
        )
        msg = data_refusal_message(exc, ds.covered_years())
        state["final_answer"] = msg
        state["data_operation"] = op.model_dump(mode="json")
        yield {"type": "token", "value": msg}
        return
    audit_record(
        state,
        event_type=audit_events.DATA_EXECUTE,
        payload={
            "ok": True,
            "row_count": result.row_count,
            "duration_s": round(result.duration_s, 3),
            "csv_sha256": ds.csv_sha256,
            "metric": result.metric,
            "aggregation": result.aggregation,
        },
    )
    yield _stage(
        "data.execute", "done", info=f"rows={result.row_count}"
    )

    # --- render --------------------------------------------------
    answer_md = data_render(result)
    op_json = op.model_dump(mode="json")
    state["final_answer"] = answer_md
    state["data_operation"] = {
        **op_json,
        "_drilldown": bool(previous_op),
    }
    state["last_data_operation"] = op_json
    yield {"type": "token", "value": answer_md}


def _emit_terminal_text(
    state: GraphState, route: str, node_name: str
) -> Iterator[dict]:
    """Used by decline / clarifier / fallback - same shape as a chat reply."""
    yield _stage(node_name, "started")
    if node_name == "decline":
        state.update(decline_node(state))
    elif node_name == "clarifier":
        state.update(clarifier_node(state))
    elif node_name == "fallback":
        state.update(fallback_node(state))
    yield _stage(node_name, "done")
    yield {"type": "token", "value": state.get("final_answer", "")}
    yield {
        "type": "done",
        "citations": [],
        "validated": True,
        "retry_count": 0,
        "critique": "",
        "route": route,
        "target_year": state.get("target_year"),
        "fallback_offered": state.get("fallback_offered"),
        "clarifier_reason": state.get("clarifier_reason"),
    }


def stream_graph(
    question: str,
    history: list[dict] | None = None,
    user_activity: list[dict] | None = None,
    user_id: str | None = None,
    conversation_id: int | None = None,
) -> Iterator[dict]:
    """Walk supervisor -> one of the seven terminal branches.

    Branches: decline / clarifier / fallback / data / report
    or rag (+ validator + 1-retry loop).
    """
    state: GraphState = {
        "question": question,
        "retry_count": 0,
        "history": history or [],
        "user_activity": user_activity or [],
    }
    if user_id is not None:
        state["user_id"] = user_id
    if conversation_id is not None:
        state["conversation_id"] = conversation_id

    try:
        # --- Supervisor ---
        yield _stage("supervisor", "started")
        state.update(supervisor_node(state))
        route = state.get("route") or "rag"
        info = f"route={route}"
        ty = state.get("target_year")
        if ty is not None:
            info += f" year={ty}"
        yield _stage("supervisor", "done", info=info)

        # --- Terminal branches (no validator loop) ---
        if route == "out_of_scope":
            yield from _emit_terminal_text(state, route, "decline")
            return
        if route == "needs_clarification":
            yield from _emit_terminal_text(state, route, "clarifier")
            return
        if route == "out_of_year":
            yield from _emit_terminal_text(state, route, "fallback")
            return

        # --- Phase 8 data branch (plan + execute sub-stages) ---
        if route == "data":
            yield _stage("data", "started")
            yield from _run_data_streaming(state)
            yield _stage("data", "done")
            yield {
                "type": "done",
                "citations": [],
                "validated": True,
                "retry_count": 0,
                "critique": "",
                "route": route,
                "target_year": state.get("target_year"),
                "data_operation": state.get("data_operation"),
            }
            return

        # --- Report branch ---
        if route == "report":
            yield _stage("report", "started")
            state.update(report_node(state))
            yield _stage("report", "done")
            yield {"type": "token", "value": state.get("final_answer", "")}
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
                "target_year": state.get("target_year"),
                # Phase 9 - the executive-pipeline path sets these
                # on state so the UI can render download buttons +
                # the run-id caption. Legacy policy-summary reports
                # leave them None / "".
                "report_kind": state.get("report_kind"),
                "report_year": state.get("report_year"),
                "report_run_id": state.get("report_run_id"),
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
            "target_year": state.get("target_year"),
        }
    except Exception as exc:  # noqa: BLE001
        log.exception("stream_graph error")
        yield {"type": "error", "value": str(exc)}
