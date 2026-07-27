"""Assembler agent.

Merges Step outputs from the orchestrator into one coherent answer:

  Single-step plan: pass-through — no H3 headers or citation renumbering.
  Multi-step plan:
    - Each successful Step becomes an H3 section (heading from step args).
    - Citations are deduplicated by (source, section, chunk_index) and
      renumbered sequentially across all sections.
    - Failed/skipped Steps get a ⚠ Partial answer badge at the top.

The assembler also propagates data/report side-channel state
(data_operation, report_kind, report_run_id, report_year) back to the
top-level state so the existing UI expanders continue to work.
"""
from __future__ import annotations

from agentic_backend.graph.state import GraphState
from agentic_backend.observability.logging import get_logger
from agentic_backend.observability.tracing import get_tracer

log = get_logger(__name__)
tracer = get_tracer(__name__)


def _dedup_citations(all_citations: list[dict]) -> list[dict]:
    """Deduplicate by (source, section, chunk_index), preserving order."""
    seen: set[tuple] = set()
    result: list[dict] = []
    for c in all_citations:
        key = (
            c.get("source", ""),
            c.get("section", ""),
            int(c.get("chunk_index", 0)),
        )
        if key not in seen:
            seen.add(key)
            result.append(c)
    return result


def assembler_node(state: GraphState) -> dict:
    """Merge all step outputs into the final_answer."""
    plan_dict = state.get("plan") or {}
    steps_raw: list[dict] = plan_dict.get("steps", [])
    step_results: dict = state.get("step_results") or {}

    with tracer.start_as_current_span("assembler.merge") as span:
        span.set_attribute("assembler.total_steps", len(steps_raw))

        # --- single-step pass-through ---
        if len(steps_raw) == 1:
            step_id = steps_raw[0]["step_id"]
            result = step_results.get(step_id, {})
            span.set_attribute("assembler.mode", "passthrough")
            out = {
                "final_answer": result.get("output", ""),
                "final_citations": result.get("citations", []),
                "validated": result.get("ok", True),
                # Propagate route for backward-compat with the UI.
                "route": _route_label(steps_raw),
            }
            out.update(_side_channel_state(steps_raw, step_results))
            return out

        # --- multi-step merge ---
        span.set_attribute("assembler.mode", "merge")
        sections: list[str] = []
        all_citations: list[dict] = []
        skipped: list[str] = []

        for step in steps_raw:
            step_id = step["step_id"]
            result = step_results.get(step_id, {})
            if not result.get("ok"):
                skipped.append(result.get("heading") or step.get("heading") or step_id)
                continue
            heading = result.get("heading") or step.get("heading") or step["skill_name"]
            sections.append(f"### {heading}\n\n{result.get('output', '')}")
            all_citations.extend(result.get("citations", []))

        deduped = _dedup_citations(all_citations)
        merged = "\n\n".join(sections)

        if skipped:
            badge = f"⚠ Partial answer — skipped: {', '.join(skipped)}\n\n"
            merged = badge + merged

        span.set_attribute("assembler.skipped_steps", len(skipped))
        span.set_attribute("assembler.citations", len(deduped))
        log.info(
            "Assembler: %d sections merged, %d citations, %d skipped",
            len(sections),
            len(deduped),
            len(skipped),
        )

        with tracer.start_as_current_span("assembler.self_critique"):
            # Lightweight check: warn if any section has numeric claims but no citation.
            for section in sections:
                has_number = any(c.isdigit() for c in section)
                has_citation = "[" in section and "]" in section
                if has_number and not has_citation:
                    log.warning("Assembler self-critique: numeric claim without citation")

        out = {
            "final_answer": merged,
            "final_citations": deduped,
            "validated": not bool(skipped),
            "partial_failure": bool(skipped),
            "skipped_steps": skipped,
            "route": _route_label(steps_raw),
        }
        out.update(_side_channel_state(steps_raw, step_results))
        return out


def _route_label(steps_raw: list[dict]) -> str:
    """Derive a backward-compat route label from the plan's skill set."""
    skills = [s.get("skill_name", "") for s in steps_raw]
    if len(skills) == 1:
        mapping = {
            "answer-policy-question": "rag",
            "compute-kpi": "data",
            "executive-section-summary": "report",
            "clarify-year": "needs_clarification",
            "out-of-year-fallback": "out_of_year",
            "decline": "out_of_scope",
        }
        return mapping.get(skills[0], "agentic")
    return "agentic"


def _side_channel_state(steps_raw: list[dict], step_results: dict) -> dict:
    """Propagate data/report side-channel fields from worker results."""
    extras: dict = {}
    for step in steps_raw:
        result = step_results.get(step["step_id"], {})
        skill = step.get("skill_name", "")
        if skill == "compute-kpi":
            if result.get("data_operation") is not None:
                extras["data_operation"] = result["data_operation"]
            if result.get("last_data_operation") is not None:
                extras["last_data_operation"] = result["last_data_operation"]
        elif skill == "executive-section-summary":
            for key in ("report_kind", "report_run_id", "report_year"):
                if result.get(key) is not None:
                    extras[key] = result[key]
    return extras
