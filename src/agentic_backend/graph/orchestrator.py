"""Orchestrator — DAG walker and generic worker dispatcher.

Graph topology:

    planner  -->  orchestrator  -->  [Send("worker", ...) for ready steps]
                       ^                          |
                       |__________________________|  (loop back until done)
                       |
                   "assembler"  (when all steps complete or deadlocked)

The orchestrator_node is a no-op relay; all routing logic lives in
route_orchestrator, which is registered as a conditional edge on the
"orchestrator" node in builder.py.

worker_node is the generic dispatcher: it looks up the Skill, builds a
step-specific state slice, and calls the appropriate underlying agent
(rag, data, report, clarifier, fallback). Results are written back as
a step_results dict entry with the merge-reducer (Annotated field in
GraphState) so parallel workers never clobber each other.
"""
from __future__ import annotations

import dataclasses
import time

from langgraph.types import Send

from agentic_backend.graph.state import GraphState
from agentic_backend.observability.logging import get_logger
from agentic_backend.observability.metrics import track_skill
from agentic_backend.observability.tracing import get_tracer

log = get_logger(__name__)
tracer = get_tracer(__name__)

# Max steps / tool-calls per turn (budget guard from spec).
_MAX_STEPS_PER_TURN = 10


# ---------------------------------------------------------------------------
# Orchestrator node (no-op relay)
# ---------------------------------------------------------------------------

def orchestrator_node(state: GraphState) -> dict:
    """No-op — routing is handled by route_orchestrator below."""
    return {}


# ---------------------------------------------------------------------------
# Conditional edge: fan-out to workers or proceed to assembler
# ---------------------------------------------------------------------------

def route_orchestrator(
    state: GraphState,
) -> list[Send] | str:
    """Return a list of Send() for each ready step, or 'assembler' when done."""
    plan_dict = state.get("plan") or {}
    steps_raw: list[dict] = plan_dict.get("steps", [])
    step_results: dict = state.get("step_results") or {}

    completed = set(step_results.keys())
    all_ids = {s["step_id"] for s in steps_raw}

    # All done or budget exceeded.
    if completed >= all_ids or len(completed) >= _MAX_STEPS_PER_TURN:
        return "assembler"

    # Find steps whose dependencies are all satisfied.
    ready = [
        s for s in steps_raw
        if s["step_id"] not in completed
        and all(dep in completed for dep in s.get("depends_on", []))
    ]

    if not ready:
        # Deadlocked (dependencies never resolve) — go to assembler.
        log.warning(
            "Orchestrator: deadlock detected (completed=%s, pending=%s) "
            "— routing to assembler",
            sorted(completed),
            sorted(all_ids - completed),
        )
        return "assembler"

    log.info(
        "Orchestrator: dispatching %d step(s): %s",
        len(ready),
        [s["step_id"] for s in ready],
    )
    return [Send("worker", {**state, "current_step": s}) for s in ready]


# ---------------------------------------------------------------------------
# Worker node — generic skill dispatcher
# ---------------------------------------------------------------------------

def worker_node(state: GraphState) -> dict:
    """Execute one Step by dispatching to the appropriate underlying agent."""
    current_step: dict = state.get("current_step") or {}
    step_id: str = current_step.get("step_id", "unknown")
    skill_name: str = current_step.get("skill_name", "")
    args: dict = current_step.get("args") or {}
    heading: str = current_step.get("heading") or skill_name

    log.info("Worker: step=%s skill=%s", step_id, skill_name)

    with tracer.start_as_current_span(f"worker.{skill_name}") as span, \
            track_skill(skill_name, route="agentic"):
        span.set_attribute("worker.step_id", step_id)
        span.set_attribute("worker.skill_name", skill_name)
        t0 = time.perf_counter()

        try:
            output, citations, ok, error, extras = _dispatch(
                skill_name, args, state
            )
        except Exception as exc:  # noqa: BLE001 — worker isolation
            log.exception("Worker step %s (%s) failed: %s", step_id, skill_name, exc)
            output, citations, ok, error, extras = "", [], False, str(exc), {}

        elapsed = time.perf_counter() - t0
        span.set_attribute("worker.duration_s", round(elapsed, 3))
        span.set_attribute("worker.ok", ok)
        if not ok:
            span.set_attribute("worker.error", error[:200])

        log.info(
            "Worker done: step=%s ok=%s chars=%d duration=%.2fs",
            step_id,
            ok,
            len(output),
            elapsed,
        )

    step_result = {
        "step_id": step_id,
        "skill_name": skill_name,
        "output": output,
        "citations": citations,
        "ok": ok,
        "error": error,
        "heading": heading,
        **extras,
    }
    return {"step_results": {step_id: step_result}}


# ---------------------------------------------------------------------------
# Skill dispatch table
# ---------------------------------------------------------------------------

def _dispatch(
    skill_name: str,
    args: dict,
    state: GraphState,
) -> tuple[str, list[dict], bool, str, dict]:
    """Route to the appropriate underlying agent.

    Returns:
        (output_text, citations_list, ok, error_msg, extras_dict)
        extras_dict carries phase-specific fields (data_operation, etc.)
    """
    if skill_name == "answer-policy-question":
        return _invoke_rag(args, state)
    if skill_name == "compute-kpi":
        return _invoke_data(args, state)
    if skill_name == "executive-section-summary":
        return _invoke_report(args, state)
    if skill_name == "clarify-year":
        return _invoke_clarifier(args, state)
    if skill_name == "out-of-year-fallback":
        return _invoke_fallback(args, state)
    if skill_name == "decline":
        return _invoke_decline(args, state)

    return (
        f"(unknown skill: {skill_name})",
        [],
        False,
        f"No handler registered for skill '{skill_name}'",
        {},
    )


def _step_state(state: GraphState, args: dict) -> GraphState:
    """Build a step-local state slice with args-driven overrides."""
    overrides: dict = {}
    if "query" in args:
        overrides["question"] = args["query"]
    if "question" in args:
        overrides["question"] = args["question"]
    if "year" in args and args["year"] is not None:
        overrides["target_year"] = int(args["year"])
    return {**state, **overrides}  # type: ignore[return-value]


def _chunks_to_dicts(chunks: list) -> list[dict]:
    """Serialise RetrievedChunk objects to plain dicts for state storage."""
    result = []
    for c in chunks or []:
        if isinstance(c, dict):
            result.append(c)
        elif dataclasses.is_dataclass(c):
            result.append(dataclasses.asdict(c))
        else:
            result.append({"source": str(c), "content": "", "section": ""})
    return result


def _invoke_rag(
    args: dict, state: GraphState
) -> tuple[str, list[dict], bool, str, dict]:
    """Run RAG + inline validator loop for answer-policy-question."""
    from agentic_backend.agents.rag_agent import rag_node
    from agentic_backend.agents.validator_agent import validator_node

    step_state = _step_state(state, args)
    step_state["retry_count"] = 0
    step_state["last_critique"] = ""

    # Initial pass.
    step_state.update(rag_node(step_state))

    # Validate.
    step_state.update(validator_node(step_state))
    validation = step_state.get("validation", {})

    # One retry if needed.
    if not (validation.get("grounded") and validation.get("citations_ok")):
        step_state["retry_count"] = 1
        step_state["last_critique"] = validation.get("critique", "")
        step_state.update(rag_node(step_state))
        step_state.update(validator_node(step_state))

    answer = step_state.get("final_answer") or step_state.get("draft_answer", "")
    citations = _chunks_to_dicts(
        step_state.get("final_citations") or step_state.get("chunks") or []
    )
    validated = bool(step_state.get("validated", True))
    return answer, citations, validated, "", {}


def _invoke_data(
    args: dict, state: GraphState
) -> tuple[str, list[dict], bool, str, dict]:
    """Run the Talk-to-Data pipeline for compute-kpi."""
    from agentic_backend.agents.data_agent import data_node

    step_state = _step_state(state, args)
    result = data_node(step_state)
    answer = result.get("final_answer", "")
    extras = {
        k: result[k]
        for k in ("data_operation", "last_data_operation")
        if k in result
    }
    return answer, [], True, "", extras


def _invoke_report(
    args: dict, state: GraphState
) -> tuple[str, list[dict], bool, str, dict]:
    """Run the executive report pipeline for executive-section-summary."""
    from agentic_backend.agents.report_agent import report_node

    step_state = _step_state(state, args)
    if "year" in args and args["year"] is not None:
        step_state["target_year"] = int(args["year"])
    result = report_node(step_state)
    answer = result.get("final_answer", "")
    citations = _chunks_to_dicts(result.get("final_citations") or [])
    extras = {
        k: result[k]
        for k in ("report_kind", "report_run_id", "report_year")
        if k in result
    }
    return answer, citations, True, "", extras


def _invoke_clarifier(
    args: dict, state: GraphState
) -> tuple[str, list[dict], bool, str, dict]:
    """Run the clarifier for clarify-year."""
    from agentic_backend.graph.clarifier import clarifier_node

    step_state = _step_state(state, args)
    if "reason" in args:
        step_state["clarifier_reason"] = args["reason"]
    result = clarifier_node(step_state)
    return result.get("final_answer", ""), [], True, "", {}


def _invoke_fallback(
    args: dict, state: GraphState
) -> tuple[str, list[dict], bool, str, dict]:
    """Run the out-of-year fallback for out-of-year-fallback."""
    from agentic_backend.graph.supervisor import fallback_node

    step_state = _step_state(state, args)
    if "requested_year" in args:
        step_state["target_year"] = int(args["requested_year"])
    result = fallback_node(step_state)
    return result.get("final_answer", ""), [], True, "", {}


def _invoke_decline(
    args: dict, state: GraphState
) -> tuple[str, list[dict], bool, str, dict]:
    """Return a canned out-of-scope refusal — no LLM call needed."""
    return (
        "I'm ACME's insurance assistant. I can only help with insurance "
        "policy questions, KPI metrics, and document summaries. "
        "That question is outside my scope — please ask me something "
        "related to ACME's insurance products or policies.",
        [],
        True,
        "",
        {},
    )
