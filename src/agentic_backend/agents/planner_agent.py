"""Planner agent.

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

from agentic_backend.agents.memory_agent import format_history_for_prompt
from agentic_backend.audit import events as audit_events
from agentic_backend.audit.middleware import record as audit_record
from agentic_backend.config import settings
from agentic_backend.graph.state import GraphState, is_fast_mode
from agentic_backend.llm import load_prompt
from agentic_backend.llm.ollama_client import get_fast_llm, get_llm
from agentic_backend.observability.logging import get_logger
from agentic_backend.observability.metrics import record_plan_steps
from agentic_backend.observability.tracing import get_tracer
from agentic_backend.skills import get_skill_registry, skill_catalog_for_planner

log = get_logger(__name__)
tracer = get_tracer(__name__)

_PLANNER_TEMPLATE = load_prompt("planner")
_JSON_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)
# Matches end-of-value followed by a newline and then a new key/value start —
# i.e., a missing comma between adjacent JSON properties or array elements.
_MISSING_COMMA = re.compile(r'(["\d\w\]\}])([ \t]*\n)([ \t]*)(["\{\[])')

_ANALYTICS_PATTERNS = (
    r"\bkpi\b",
    r"\btrend\b",
    r"\bforecast\b",
    r"\bdashboard\b",
    r"\bchart\b",
    r"\bbreak\s*down\b",
    r"\bgroup(ed)?\s+by\b",
    r"\byear\s*[- ]?over\s*[- ]?year\b",
    r"\byoy\b",
    r"\bloss\s+ratio\b",
    r"\bcombined\s+ratio\b",
    r"\bretention\s+rate\b",
    r"\bchurn\b",
    r"\bgwp\b|\bgross\s+written\s+premium\b",
    r"\bearned\s+premium\b",
    r"\bincurred\s+loss(es)?\b",
    r"\bpaid\s+loss(es)?\b",
    r"\bclaim(s)?\s+frequency\b",
    r"\bclaim(s)?\s+severity\b",
)
_MULTI_INTENT_CONNECTORS = (
    r"\bcompare\b",
    r"\bversus\b|\bvs\b",
    r",\s*and\s+",
)
_POLICY_PATTERNS = (
    r"\brefund\b",
    r"\bcoverage\b",
    r"\bdeductible\b",
    r"\bpolicy\b",
    r"\bexclusion\b",
    r"\beligib(le|ility)\b",
    r"\bwaiting\s+period\b",
    r"\bgrace\s+period\b",
    r"\bpayout\b",
    r"\bclaim\s+window\b",
    r"\bcopay\b|\bco-pay\b",
    r"\brider\b",
    r"\bendorsement\b",
    r"\bpre[- ]?existing\b",
    r"\bsum\s+insured\b",
)
_QUESTION_PATTERNS = (
    r"^\s*(what|when|which|who|where|why|how)\b",
    r"\bcan\s+i\b",
    r"\bis\s+there\b",
)


def _has_any_pattern(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text) is not None for pattern in patterns)


def _count_pattern_hits(text: str, patterns: tuple[str, ...]) -> int:
    return sum(1 for pattern in patterns if re.search(pattern, text) is not None)


def _resolve_fast_intent(question: str) -> str:
    """Classify query intent for fast-mode routing decisions.

    Returns one of: "policy_qa", "analytics_or_report", "multi_intent", "other".
    """
    text = question.lower().strip()

    analytics_hits = _count_pattern_hits(text, _ANALYTICS_PATTERNS)
    policy_hits = _count_pattern_hits(text, _POLICY_PATTERNS)
    is_question = "?" in question or _has_any_pattern(text, _QUESTION_PATTERNS)
    has_multi_connector = _has_any_pattern(text, _MULTI_INTENT_CONNECTORS)

    if analytics_hits > 0:
        return "analytics_or_report"

    if has_multi_connector and (policy_hits > 0 or is_question):
        return "multi_intent"

    if is_question and policy_hits > 0:
        return "policy_qa"

    return "other"


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


def _repair_json(text: str) -> str:
    """Best-effort repair of LLM JSON syntax errors (no external deps).

    Handles the three most common small-model failures:
    - Missing comma between adjacent properties/elements
    - Trailing commas before ] or }
    - JS-style // and /* */ comments
    """
    text = re.sub(r"//[^\n]*", "", text)
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    text = _MISSING_COMMA.sub(r"\1,\2\3\4", text)
    text = re.sub(r",(\s*[}\]])", r"\1", text)
    return text.strip()


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
    _MAX_QUESTION_CHARS = 2_000
    question = (state.get("question") or "")[:_MAX_QUESTION_CHARS]
    if len(state.get("question") or "") > _MAX_QUESTION_CHARS:
        log.warning(
            "Planner: question truncated to %d chars to prevent context stuffing",
            _MAX_QUESTION_CHARS,
        )
    covered_years = state.get("covered_years") or settings.kb_covered_years
    today = state.get("today") or ""
    history = state.get("history") or []

    # Clarifier follow-up: if the immediately-prior assistant turn was the clarifier,
    # the current message is the user's answer (e.g. "2024"). Stitch the original
    # question back in so intent classification and retrieval see the full intent.
    is_clarifier_followup = False
    if history:
        for _msg in reversed(history):
            _role = _msg.get("role")
            if _role == "assistant":
                is_clarifier_followup = _msg.get("route") == "needs_clarification"
                break
            if _role == "user":
                break
    if is_clarifier_followup:
        original_question: str | None = None
        for _msg in reversed(history):
            if _msg.get("role") == "user":
                _content = (_msg.get("content") or "").strip()
                if _content:
                    original_question = _content
                    break
        if original_question:
            question = f"{original_question} {question}".strip()
            log.info(
                "Planner: clarifier follow-up — stitching original=%r + reply=%r",
                original_question[:60],
                (state.get("question") or "")[:40],
            )

    # Analytics/multi-intent requests auto-promote to accurate mode for reliability.
    # Year-ambiguous policy questions fall through to the LLM planner so that
    # clarify-year and out-of-year-fallback routing is not bypassed.
    intent = _resolve_fast_intent(question)
    is_fast_mode_requested = is_fast_mode(state)
    should_force_accurate = is_fast_mode_requested and intent in {
        "analytics_or_report",
        "multi_intent",
    }
    is_effective_fast_mode = is_fast_mode_requested and not should_force_accurate

    if should_force_accurate:
        log.info("Fast mode override: using accurate planning for intent=%s", intent)
    else:
        log.info(
            "Intent resolver: intent=%s is_effective_fast_mode=%s",
            intent,
            is_effective_fast_mode,
        )

    # Deterministic policy_qa routing — the LLM alone is not reliable enough
    # for year-disambiguation, coverage checks, and clarifier follow-ups.
    # Mirrors the programmatic guards the old supervisor_node provided.
    if intent == "policy_qa":
        year_match = re.search(r"\b(20\d{2})\b", question)
        resolved_year: int | None = (
            int(year_match.group(1)) if year_match else state.get("target_year")
        )

        if resolved_year is None:
            # No year in question or history → ask for clarification.
            log.info("Planner: year_missing for policy_qa — injecting clarify-year step")
            plan_id = str(uuid.uuid4())
            with tracer.start_as_current_span("planner.plan") as span:
                span.set_attribute("planner.mode", "clarify_year")
                span.set_attribute("planner.fast_path", True)
                plan_dict = {
                    "plan_id": plan_id,
                    "self_critique_ok": True,
                    "steps": [
                        {
                            "step_id": "step-1",
                            "skill_name": "clarify-year",
                            "args": {"reason": "year_missing"},
                            "depends_on": [],
                            "heading": "Clarification",
                        }
                    ],
                }
                record_plan_steps(1)
                audit_record(
                    dict(state),
                    event_type=audit_events.PLANNER_PLAN,
                    payload={
                        "plan_id": plan_id,
                        "steps": 1,
                        "step_skills": ["clarify-year"],
                        "duration_s": 0.0,
                        "fast_path": True,
                        "reason": "year_missing",
                    },
                )
            return {
                "plan": plan_dict,
                "planner_intent": intent,
                "response_mode": "fast" if is_effective_fast_mode else "accurate",
                "step_results": {},
                "partial_failure": False,
                "skipped_steps": [],
            }

        if resolved_year not in covered_years:
            # Year found but not in KB → out-of-year fallback.
            log.info(
                "Planner: year %d not covered — injecting out-of-year-fallback step",
                resolved_year,
            )
            plan_id = str(uuid.uuid4())
            with tracer.start_as_current_span("planner.plan") as span:
                span.set_attribute("planner.mode", "out_of_year")
                span.set_attribute("planner.fast_path", True)
                plan_dict = {
                    "plan_id": plan_id,
                    "self_critique_ok": True,
                    "steps": [
                        {
                            "step_id": "step-1",
                            "skill_name": "out-of-year-fallback",
                            "args": {"requested_year": resolved_year},
                            "depends_on": [],
                            "heading": "Year Not Available",
                        }
                    ],
                }
                record_plan_steps(1)
                audit_record(
                    dict(state),
                    event_type=audit_events.PLANNER_PLAN,
                    payload={
                        "plan_id": plan_id,
                        "steps": 1,
                        "step_skills": ["out-of-year-fallback"],
                        "duration_s": 0.0,
                        "fast_path": True,
                        "reason": "out_of_year",
                    },
                )
            return {
                "plan": plan_dict,
                "planner_intent": intent,
                "response_mode": "fast" if is_effective_fast_mode else "accurate",
                "step_results": {},
                "partial_failure": False,
                "skipped_steps": [],
            }

        # Year resolved and in KB — skip LLM for deterministic cases.
        if is_clarifier_followup or is_effective_fast_mode:
            log.info(
                "Planner: policy_qa year=%d covered — injecting answer-policy-question "
                "(clarifier_followup=%s fast_mode=%s)",
                resolved_year,
                is_clarifier_followup,
                is_effective_fast_mode,
            )
            plan_id = str(uuid.uuid4())
            planner_mode = "clarifier_followup" if is_clarifier_followup else "fast_path"
            with tracer.start_as_current_span("planner.plan") as span:
                span.set_attribute("planner.mode", planner_mode)
                span.set_attribute("planner.fast_path", True)
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
                record_plan_steps(1)
                audit_record(
                    dict(state),
                    event_type=audit_events.PLANNER_PLAN,
                    payload={
                        "plan_id": plan_id,
                        "steps": 1,
                        "step_skills": ["answer-policy-question"],
                        "duration_s": 0.0,
                        "fast_path": True,
                        "reason": planner_mode,
                    },
                )
            return {
                "plan": plan_dict,
                "planner_intent": intent,
                "response_mode": "fast" if is_effective_fast_mode else "accurate",
                "step_results": {},
                "partial_failure": False,
                "skipped_steps": [],
            }

    with tracer.start_as_current_span("planner.plan") as span:
        span.set_attribute("question.preview", question[:80])
        planner_mode = "fast" if is_effective_fast_mode else "accurate"
        span.set_attribute("planner.mode", planner_mode)
        span.set_attribute("planner.model", settings.planner_model)

        plan_id = str(uuid.uuid4())
        catalog = skill_catalog_for_planner()
        history_block = format_history_for_prompt(history, max_turns=2)
        history_section = (
            f"<conversation_history>\n{history_block}\n</conversation_history>"
            if history_block
            else ""
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
        planner_llm = get_fast_llm() if is_effective_fast_mode else get_llm()
        result = planner_llm.invoke(
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

        # Parse JSON plan — try raw first, then best-effort repair.
        extracted = _extract_json(raw)
        try:
            plan_dict = json.loads(extracted)
        except json.JSONDecodeError:
            try:
                plan_dict = json.loads(_repair_json(extracted))
                log.info("Planner JSON repaired successfully")
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
        record_plan_steps(n_steps)
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
        "planner_intent": intent,
        "response_mode": "fast" if is_effective_fast_mode else "accurate",
        "step_results": {},
        "partial_failure": False,
        "skipped_steps": [],
    }
