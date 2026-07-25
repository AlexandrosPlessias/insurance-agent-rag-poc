"""streaming orchestrator.

Walks the Planner → Orchestrator → Workers → Assembler pipeline and emits
NDJSON events. Pre-execution approval gates can suspend the
plan and emit an `approval_required` event when a Skill has requires_approval=True.

Event types emitted:
  {"type": "stage",            "node": "planner",   "status": "started"|"done"}
  {"type": "stage",            "node": "worker.…",  "status": "started"|"done"}
  {"type": "stage",            "node": "assembler", "status": "started"|"done"}
  {"type": "token",            "value": "…"}
  {"type": "meta",             "reformulated_query": "…"}
  {"type": "approval_required","plan_id": "…", "step_id": "…",
                                "message": "…", "expires_at": "…",
                                "trigger_case": "…"}
  {"type": "done",             "citations": […], "validated": bool, "route": "…", …}
  {"type": "error",            "value": "…"}
"""

from __future__ import annotations

import dataclasses
import re
import time
from typing import Iterator

from langchain_core.messages import HumanMessage, SystemMessage

from agentic_backend.agents.assembler_agent import assembler_node
from agentic_backend.agents.planner_agent import planner_node
from agentic_backend.agents.rag_agent import (
    _extract_refund_window_answer,
    build_rag_prompt,
    citation_payload,
    rag_node,
    reformulate_question,
)
from agentic_backend.agents.validator_agent import validator_node
from agentic_backend.approvals.channels import get_channel
from agentic_backend.approvals.store import ApprovalStore
from agentic_backend.audit import events as audit_events
from agentic_backend.audit.middleware import record as audit_record
from agentic_backend.config import settings
from agentic_backend.graph.orchestrator import _step_state, worker_node
from agentic_backend.graph.state import GraphState, is_fast_mode
from agentic_backend.llm.ollama_client import get_llm
from agentic_backend.observability.logging import get_logger
from agentic_backend.observability.metrics import track_node, track_skill, track_tool
from agentic_backend.rag.retriever import retrieve
from agentic_backend.skills import get_skill_registry

log = get_logger(__name__)

_MAX_STEPS = 10


def _stage(node: str, status: str, info: str = "") -> dict:
    event: dict = {"type": "stage", "node": node, "status": status}
    if info:
        event["info"] = info
    return event


def _stream_rag_step(step: dict, state: GraphState) -> Iterator[dict]:
    """Stream tokens for an answer-policy-question step inline."""
    args = step.get("args") or {}
    step_state = _step_state(state, args)
    question = step_state.get("question") or ""
    target_year = step_state.get("target_year")
    history = step_state.get("history") or []
    where_filter = {"year": int(target_year)} if target_year is not None else None

    with track_tool("answer-policy-question", "reformulate"):
        yield _stage(f"worker.{step['step_id']}.reformulate", "started")
        reformulated = reformulate_question(question, history=history)
        step_state["reformulated_query"] = reformulated
        yield _stage(f"worker.{step['step_id']}.reformulate", "done")
    yield {"type": "meta", "reformulated_query": reformulated}

    with track_tool("answer-policy-question", "retrieve"):
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
        yield _stage(f"worker.{step['step_id']}.retrieve", "done", info=f"k={len(chunks)}")

    with track_tool("answer-policy-question", "answer"):
        yield _stage(f"worker.{step['step_id']}.answer", "started")
        extracted = (
            _extract_refund_window_answer(question, chunks) if is_fast_mode(state) else None
        )
        if extracted:
            answer_text = extracted
            yield {"type": "token", "value": answer_text}
        else:
            prompt = build_rag_prompt(chunks, history=history)
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
        yield _stage(f"worker.{step['step_id']}.answer", "done", info=f"chars={len(answer_text)}")

    # Validate — first pass
    yield _stage(f"worker.{step['step_id']}.validate", "started")
    with track_tool("answer-policy-question", "validate"):
        step_state.update(validator_node(step_state))
    v = step_state.get("validation", {})
    is_valid = bool(v.get("grounded") and v.get("citations_ok"))
    yield _stage(f"worker.{step['step_id']}.validate", "done", info=f"ok={is_valid}")

    # One retry if needed.
    if not is_valid:
        step_state["retry_count"] = 1
        step_state["last_critique"] = v.get("critique", "")
        yield _stage(f"worker.{step['step_id']}.answer", "started", info="retry")
        with track_tool("answer-policy-question", "answer_retry"):
            step_state.update(rag_node(step_state))
        answer_text = step_state.get("draft_answer", answer_text)
        yield _stage(f"worker.{step['step_id']}.answer", "done", info="retry")
        yield _stage(f"worker.{step['step_id']}.validate", "started", info="retry")
        with track_tool("answer-policy-question", "validate_retry"):
            step_state.update(validator_node(step_state))
        yield _stage(f"worker.{step['step_id']}.validate", "done", info="retry")
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


def _has_large_figure(text: str, threshold: float) -> bool:
    """Return True if any standalone number in text exceeds threshold."""
    for match in re.finditer(r"\b\d[\d,]*(?:\.\d+)?\b", text):
        try:
            if float(match.group().replace(",", "")) > threshold:
                return True
        except ValueError:
            pass
    return False


def _suspend_for_approval(
    *,
    step: dict,
    state: GraphState,
    plan_id: str,
    user_id: str,
    conversation_id: int | None,
    trigger_case: str = "",
    message: str = "",
) -> Iterator[dict]:
    """Persist the plan, issue a token, notify the channel, yield approval_required."""
    step_id: str = step["step_id"]
    skill_name: str = step.get("skill_name", "")
    if not trigger_case:
        trigger_case = "report" if skill_name == "executive-section-summary" else "pre-execution"
    if not message:
        message = _approval_message(skill_name, trigger_case)

    resume_payload = {
        "question": state.get("question"),
        "response_mode": state.get("response_mode"),
        "history": state.get("history") or [],
        "user_activity": state.get("user_activity") or [],
        "plan": state.get("plan") or {},
        "step_results": state.get("step_results") or {},
        "pending_step_id": step_id,
        "user_id": user_id,
        "conversation_id": conversation_id,
        "target_year": state.get("target_year"),
    }

    store = ApprovalStore(settings.database_url)
    store.create_plan(
        plan_id=plan_id,
        user_id=user_id,
        conversation_id=conversation_id,
        pending_step_id=step_id,
        trigger_case=trigger_case,
        resume_payload=resume_payload,
    )
    raw_token = store.issue_token(plan_id=plan_id, step_id=step_id)

    plan_row = store.get_plan(plan_id)
    expires_at = (plan_row or {}).get("expires_at", "")

    # Yield the UI event FIRST so the React client can render the approval card,
    # then wait 2 s before sending the Telegram notification.  The browser
    # needs that window to receive the NDJSON chunk and paint
    # the card — otherwise the phone buzzes before the UI is ready.
    log.info("Plan suspended plan_id=%s step_id=%s", plan_id, step_id)
    yield {
        "type": "approval_required",
        "plan_id": plan_id,
        "step_id": step_id,
        "message": message,
        "expires_at": expires_at,
        "trigger_case": trigger_case,
    }

    time.sleep(2)  # give browser time to render the card before notifying

    get_channel().send(
        raw_token=raw_token,
        plan_id=plan_id,
        message=message,
        expires_at=expires_at,
        trigger_case=trigger_case,
    )


def _approval_message(skill_name: str, trigger_case: str = "") -> str:
    if trigger_case == "kpi":
        return (
            f"This KPI answer contains figures above "
            f"€{settings.approvals_kpi_threshold:,.0f}. "
            "Manager approval required before delivery."
        )
    if skill_name == "executive-section-summary":
        return "An executive annual report is about to be generated. Approve to continue delivery."
    return "A step requires approval before it can run."


def stream_graph(
    question: str,
    history: list[dict] | None = None,
    user_activity: list[dict] | None = None,
    user_id: str | None = None,
    conversation_id: int | None = None,
    last_data_operation: dict | None = None,
    response_mode: str | None = None,
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
    if last_data_operation is not None:
        state["last_data_operation"] = last_data_operation
    if response_mode in {"fast", "accurate"}:
        state["response_mode"] = response_mode

    try:
        # --- Planner ---
        yield _stage("planner", "started")
        with track_node("planner", route="agentic"):
            state.update(planner_node(state))
        plan_dict = state.get("plan") or {}
        plan_id: str = plan_dict.get("plan_id") or ""
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
                s
                for s in steps_raw
                if s["step_id"] not in completed
                and all(dep in completed for dep in s.get("depends_on", []))
            ]
            if not ready:
                break

            for step in ready:
                step_id = step["step_id"]
                skill_name = step.get("skill_name", "")

                # Pre-execution approval gate
                skill = get_skill_registry().get(skill_name)
                if skill and skill.requires_approval:
                    # Close the orchestrator before suspending so the UI does
                    # not leave it stuck at "running" while waiting for approval.
                    yield _stage("orchestrator", "done", info=f"completed={len(completed)}")
                    yield from _suspend_for_approval(
                        step=step,
                        state=state,
                        plan_id=plan_id,
                        user_id=user_id or "",
                        conversation_id=conversation_id,
                    )
                    return  # generator ends — plan is suspended

                yield _stage(f"worker.{step_id}", "started", info=f"skill={skill_name}")

                if skill_name == "answer-policy-question":
                    # Inline streaming for RAG steps.
                    with track_skill("answer-policy-question", route="rag"):
                        yield from _stream_rag_step(step, state)
                else:
                    # Sync dispatch for non-RAG steps.
                    # Emit one sub-stage per tool declared by the skill so the
                    # UI can show pipeline progress even for synchronous workers.
                    skill_tools: list[str] = skill.tools_used if skill else []
                    for tool in skill_tools:
                        yield _stage(f"worker.{step_id}.{tool}", "started")

                    step_state_for_worker: GraphState = {  # type: ignore[assignment]
                        **state,
                        "current_step": step,
                    }
                    result = worker_node(step_state_for_worker)
                    step_results_update: dict = result.get("step_results", {})
                    if "step_results" not in state:
                        state["step_results"] = {}  # type: ignore[index]
                    state["step_results"].update(step_results_update)  # type: ignore[index]
                    step_result = step_results_update.get(step_id, {})

                    for tool in skill_tools:
                        yield _stage(f"worker.{step_id}.{tool}", "done")

                    # Post-execution KPI gate (Case 3): check BEFORE emitting
                    # tokens so large figures never reach the user without sign-off.
                    # The result is already in state["step_results"], so resume
                    # skips re-execution and goes straight to the assembler.
                    if skill_name == "compute-kpi" and _has_large_figure(
                        step_result.get("output") or "", settings.approvals_kpi_threshold
                    ):
                        yield _stage(f"worker.{step_id}", "done")
                        completed.add(step_id)
                        iterations += 1
                        yield _stage("orchestrator", "done", info=f"completed={len(completed)}")
                        yield from _suspend_for_approval(
                            step=step,
                            state=state,
                            plan_id=plan_id,
                            user_id=user_id or "",
                            conversation_id=conversation_id,
                            trigger_case="kpi",
                        )
                        return

                    # Normal delivery: emit the primary output as tokens.
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
            "intent": state.get("planner_intent", ""),
            "effective_response_mode": state.get("response_mode"),
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


def stream_plan_resume(plan_id: str) -> Iterator[dict]:
    """Resume a suspended plan after approval.

    Reconstructs state from the persisted resume_payload, executes the
    pending step and any remaining steps, then runs the Assembler.
    The plan state is updated to 'done' on success.
    """
    store = ApprovalStore(settings.database_url)
    plan_db = store.get_plan(plan_id)

    if plan_db is None:
        yield {"type": "error", "value": f"Plan {plan_id!r} not found"}
        return
    if plan_db["state"] != "approved":
        yield {
            "type": "error",
            "value": f"Plan {plan_id!r} cannot resume — state={plan_db['state']!r}",
        }
        return

    payload = plan_db["resume_payload"]

    state: GraphState = {  # type: ignore[assignment]
        "question": payload.get("question", ""),
        "retry_count": 0,
        "step_results": payload.get("step_results") or {},
        "history": payload.get("history") or [],
        "user_activity": payload.get("user_activity") or [],
        "plan": payload.get("plan") or {},
    }
    if payload.get("response_mode") in {"fast", "accurate"}:
        state["response_mode"] = payload["response_mode"]  # type: ignore[index]
    if payload.get("user_id"):
        state["user_id"] = payload["user_id"]  # type: ignore[index]
    if payload.get("conversation_id") is not None:
        state["conversation_id"] = payload["conversation_id"]  # type: ignore[index]
    if payload.get("target_year") is not None:
        state["target_year"] = int(payload["target_year"])  # type: ignore[index]

    plan_dict: dict = state.get("plan") or {}  # type: ignore[assignment]
    steps_raw: list[dict] = plan_dict.get("steps", [])
    completed: set[str] = set((state.get("step_results") or {}).keys())
    iterations = 0
    tokens_emitted = False  # tracks whether any worker streamed tokens

    try:
        yield _stage("orchestrator", "started", info="resume")

        while True:
            all_ids = {s["step_id"] for s in steps_raw}
            if completed >= all_ids or iterations >= _MAX_STEPS:
                break

            ready = [
                s
                for s in steps_raw
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
                    tokens_emitted = True
                    yield from _stream_rag_step(step, state)
                else:
                    resume_skill = get_skill_registry().get(skill_name)
                    resume_skill_tools: list[str] = resume_skill.tools_used if resume_skill else []
                    for tool in resume_skill_tools:
                        yield _stage(f"worker.{step_id}.{tool}", "started")

                    step_state_for_worker: GraphState = {  # type: ignore[assignment]
                        **state,
                        "current_step": step,
                    }
                    result = worker_node(step_state_for_worker)
                    step_results_update: dict = result.get("step_results", {})
                    if "step_results" not in state:
                        state["step_results"] = {}  # type: ignore[index]
                    state["step_results"].update(step_results_update)  # type: ignore[index]
                    step_result = step_results_update.get(step_id, {})

                    for tool in resume_skill_tools:
                        yield _stage(f"worker.{step_id}.{tool}", "done")

                    if step_result.get("output"):
                        tokens_emitted = True
                        yield {"type": "token", "value": step_result["output"]}

                yield _stage(f"worker.{step_id}", "done")
                completed.add(step_id)
                iterations += 1

        yield _stage("orchestrator", "done", info=f"completed={len(completed)}")

        yield _stage("assembler", "started")
        assembler_result = assembler_node(state)
        state.update(assembler_result)
        yield _stage("assembler", "done")

        # Post-execution gate resumes (e.g. KPI Case 3) skip the worker loop
        # entirely because the step result is pre-computed.  The assembler has
        # the final answer but nothing was streamed — emit it now.
        if not tokens_emitted:
            final_answer = state.get("final_answer") or ""
            if final_answer:
                yield {"type": "token", "value": final_answer}

        citations_raw = state.get("final_citations") or []
        citations_out: list[dict] = []
        for c in citations_raw:
            if isinstance(c, dict):
                citations_out.append(c)
            elif dataclasses.is_dataclass(c):
                citations_out.append(citation_payload(c))

        store.update_plan_state(plan_id, "done")

        yield {
            "type": "done",
            "citations": citations_out,
            "validated": bool(state.get("validated", True)),
            "retry_count": state.get("retry_count", 0),
            "critique": "",
            "route": state.get("route", "agentic"),
            "target_year": state.get("target_year"),
            "plan_id": plan_id,
            "data_operation": state.get("data_operation"),
            "report_kind": state.get("report_kind"),
            "report_year": state.get("report_year"),
            "report_run_id": state.get("report_run_id"),
        }

    except Exception as exc:  # noqa: BLE001
        log.exception("stream_plan_resume error plan_id=%s", plan_id)
        yield {"type": "error", "value": str(exc)}
