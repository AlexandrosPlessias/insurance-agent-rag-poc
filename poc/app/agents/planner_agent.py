"""Phase 11 Planner agent.

One LLM call (qwen2.5:3b fast model) converts the user's question into a
typed Plan: a DAG of Steps. After generation, a programmatic self-critique
validates three invariants before the plan is published to the orchestrator:

  1. Every skill_name exists in the Skill registry.
  2. The dependency graph is acyclic (topological sort).
  3. No Step depends on a step_id that doesn't exist in the plan.

Security boundary: `skill_catalog_for_planner()` exposes only Skill name,
description, and input_fields — never system_prompt — so the Planner cannot
be used to exfiltrate internal instructions via prompt injection.
"""
from __future__ import annotations

import json
import re
import time
import uuid

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.memory_agent import format_history_for_prompt
from app.audit import events as audit_events
from app.audit.middleware import record as audit_record
from app.config import settings
from app.graph.state import GraphState
from app.llm import load_prompt
from app.llm.ollama_client import get_fast_llm
from app.observability.logging import get_logger
from app.observability.tracing import get_tracer
from app.skills import get_skill_registry, skill_catalog_for_planner

log = get_logger(__name__)
tracer = get_tracer(__name__)

_PLANNER_TEMPLATE = load_prompt("planner")
_JSON_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


# ---------------------------------------------------------------------------
# Plan / Step helpers
# ---------------------------------------------------------------------------

def _extract_json(raw: str) -> str:
    text = _JSON_FENCE.sub("", raw.strip()).strip()
    if not text.startswith("{"):
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            text = match.group(0)
    return text


def _has_cycle(steps: list[dict]) -> bool:
    """Return True if the DAG formed by steps has a cycle."""
    graph: dict[str, list[str]] = {s["step_id"]: s.get("depends_on", []) for s in steps}
    visited: set[str] = set()
    in_stack: set[str] = set()

    def dfs(node: str) -> bool:
        visited.add(node)
        in_stack.add(node)
        for neighbour in graph.get(node, []):
            if neighbour not in visited:
                if dfs(neighbour):
                    return True
            elif neighbour in in_stack:
                return True
        in_stack.discard(node)
        return False

    return any(dfs(s["step_id"]) for s in steps if s["step_id"] not in visited)


def _self_critique(plan_dict: dict) -> tuple[dict, bool]:
    """Programmatic self-critique — mutates and returns the plan dict.

    Checks:
      1. All skill_names exist in registry → drops unknown steps (warns).
      2. All depends_on references are valid step_ids → prunes dangling deps.
      3. DAG is acyclic → clears all deps on cycle detection (failsafe).

    Returns:
        (corrected_plan_dict, critique_ok: bool)
    """
    registry = get_skill_registry()
    steps: list[dict] = plan_dict.get("steps", [])

    # 1 — Drop steps with unknown skills.
    valid: list[dict] = []
    for step in steps:
        if step.get("skill_name") not in registry:
            log.warning(
                "Planner self-critique: unknown skill %r in step %r — dropped",
                step.get("skill_name"),
                step.get("step_id"),
            )
        else:
            valid.append(step)

    # 2 — Prune dangling dependency references.
    valid_ids = {s["step_id"] for s in valid}
    for step in valid:
        step["depends_on"] = [d for d in step.get("depends_on", []) if d in valid_ids]

    # 3 — Break cycles (failsafe: clear all deps).
    if _has_cycle(valid):
        log.warning("Planner self-critique: cycle detected — clearing all dependencies")
        for step in valid:
            step["depends_on"] = []

    plan_dict["steps"] = valid
    plan_dict["self_critique_ok"] = True
    return plan_dict, bool(valid)


# ---------------------------------------------------------------------------
# Node entry point
# ---------------------------------------------------------------------------

def planner_node(state: GraphState) -> dict:
    """Convert the user question into a validated Plan dict.

    Uses qwen2.5:3b (fast lane) so planning latency stays low; the heavier
    7B is reserved for the individual workers that execute each step.
    """
    question = state.get("question") or ""
    covered_years = state.get("covered_years") or settings.kb_covered_years
    today = state.get("today") or ""
    history = state.get("history") or []

    with tracer.start_as_current_span("planner.plan") as span:
        span.set_attribute("question.preview", question[:80])
        span.set_attribute("planner.model", settings.planner_model)

        plan_id = str(uuid.uuid4())
        catalog = skill_catalog_for_planner()
        history_block = format_history_for_prompt(history, max_turns=2)
        history_section = (
            f"Recent conversation:\n{history_block}" if history_block else ""
        )

        prompt = _PLANNER_TEMPLATE.format(
            today=today,
            covered_years=covered_years,
            skill_catalog=catalog,
            history_block=history_section,
            question=question,
            plan_id=plan_id,
        )

        t0 = time.perf_counter()
        result = get_fast_llm().invoke(
            [
                SystemMessage(content=prompt),
                HumanMessage(content=question),
            ]
        )
        elapsed = time.perf_counter() - t0
        raw = str(result.content)
        span.set_attribute("planner.duration_s", round(elapsed, 3))
        span.set_attribute("planner.output_chars", len(raw))
        log.info("Planner LLM returned %d chars in %.2fs", len(raw), elapsed)

        # Parse JSON plan.
        try:
            plan_dict = json.loads(_extract_json(raw))
        except json.JSONDecodeError as exc:
            log.warning("Planner output not valid JSON (%s) — single RAG fallback", exc)
            plan_dict = {
                "plan_id": plan_id,
                "steps": [
                    {
                        "step_id": "step-1",
                        "skill_name": "answer-policy-question",
                        "args": {"query": question},
                        "depends_on": [],
                        "heading": "Answer",
                    }
                ],
            }

        plan_dict["plan_id"] = plan_id

        # Programmatic self-critique.
        with tracer.start_as_current_span("planner.self_critique"):
            plan_dict, is_valid = _self_critique(plan_dict)
            if not is_valid:
                log.warning("Self-critique removed all steps — single RAG fallback")
                plan_dict = {
                    "plan_id": plan_id,
                    "self_critique_ok": True,
                    "steps": [
                        {
                            "step_id": "step-1",
                            "skill_name": "answer-policy-question",
                            "args": {"query": question},
                            "depends_on": [],
                            "heading": "Answer",
                        }
                    ],
                }

        n_steps = len(plan_dict.get("steps", []))
        span.set_attribute("planner.steps", n_steps)
        log.info(
            "Plan ready: id=%s steps=%d",
            plan_dict.get("plan_id"),
            n_steps,
        )

        audit_record(
            state,
            event_type=audit_events.PLANNER_PLAN,
            payload={
                "plan_id": plan_dict.get("plan_id"),
                "steps": n_steps,
                "step_skills": [s.get("skill_name") for s in plan_dict.get("steps", [])],
                "duration_s": round(elapsed, 3),
            },
        )

    return {
        "plan": plan_dict,
        "step_results": {},
        "partial_failure": False,
        "skipped_steps": [],
    }
