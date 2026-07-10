"""per-section narrator.

One LLM call per section, grounded in that section's structured
inputs only. Three sections need prose:

  executive_summary       4-6 sentence top-of-report narrative
  yearly_narrative        4 paragraphs, one per business pillar
  recommendations         3-5 typed action items as JSON

Everything else (KPI grid, trend charts, risk indicators, appendix
table) is rendered deterministically by the collector and the
writers - no LLM ever touches the numbers.

Bounded fault tolerance: if the LLM call fails or its output can't
be parsed, the section's narrative_md / items list falls back to a
templated placeholder. The report still renders.
"""
from __future__ import annotations

import json
import re

from langchain_core.messages import HumanMessage, SystemMessage

from agentic_backend.llm import load_prompt
from agentic_backend.llm.ollama_client import get_llm
from agentic_backend.observability.logging import get_logger
from agentic_backend.observability.tracing import get_tracer
from agentic_backend.rag.retriever import RetrievedChunk
from agentic_backend.reporting.executive.collector import CollectedInputs
from agentic_backend.reporting.executive.sections import (
    ExecutiveSummarySection,
    Recommendation,
    RecommendationsSection,
    YearlyNarrativeSection,
)

log = get_logger(__name__)
tracer = get_tracer(__name__)

_SUMMARY_PROMPT = load_prompt("executive/summary")
_NARRATIVE_PROMPT = load_prompt("executive/narrative")
_RECOMMENDATIONS_PROMPT = load_prompt("executive/recommendations")


# ---------------------------------------------------------------------
# Prompt-input serialisation
# ---------------------------------------------------------------------


def _chunks_to_payload(chunks: list[RetrievedChunk]) -> list[dict]:
    """Compact JSON-safe representation of the policy chunks the
    recommendations narrator may cite. Drops the chunk body to keep
    the prompt small - the narrator only needs source + section."""
    return [
        {
            "source": c.source,
            "section": c.section_title or c.section,
            "snippet": (c.content[:160] + "...") if len(c.content) > 160
                       else c.content,
        }
        for c in chunks
    ]


def _risk_payload(indicators: list) -> list[dict]:
    return [
        {
            "label": r.label,
            "value": r.value_str,
            "severity": r.severity,
        }
        for r in indicators
    ]


def _invoke_llm(prompt: str, label: str) -> str:
    """Single-shot LLM call with span + timing. Returns the raw text."""
    with tracer.start_as_current_span(f"report.{label}") as span:
        span.set_attribute("report.section", label)
        result = get_llm().invoke(
            [
                SystemMessage(content=prompt),
                HumanMessage(content="Generate the section now."),
            ]
        )
        text = str(result.content).strip()
        span.set_attribute("report.output_chars", len(text))
        log.info(
            "narrator: %s LLM returned %d chars", label, len(text)
        )
        return text


# ---------------------------------------------------------------------
# Section narrators
# ---------------------------------------------------------------------


def narrate_executive_summary(inputs: CollectedInputs) -> ExecutiveSummarySection:
    section = ExecutiveSummarySection(
        headline_metrics=inputs.headline_metrics,
    )
    prompt = _SUMMARY_PROMPT.format(
        year=inputs.year,
        compare_to_year=inputs.compare_to_year,
        headline_metrics_json=json.dumps(
            inputs.headline_metrics, indent=2,
        ),
    )
    try:
        section.narrative_md = _invoke_llm(prompt, "summary")
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "executive summary narration failed (%s); using fallback",
            exc,
        )
        section.narrative_md = (
            f"In {inputs.year} ACME Insurances posted gross written "
            f"premium of €{inputs.headline_metrics.get('gwp_eur', 0):,} "
            f"({inputs.headline_metrics.get('gwp_yoy_pct', 0):+.1f}% vs "
            f"{inputs.compare_to_year}), with a loss ratio of "
            f"{inputs.headline_metrics.get('loss_ratio_pct', 0):.1f}% "
            f"and an NPS of "
            f"{inputs.headline_metrics.get('nps_score', 0):+d}."
        )
    return section


def narrate_yearly_narrative(inputs: CollectedInputs) -> YearlyNarrativeSection:
    section = YearlyNarrativeSection(
        inputs=inputs.yearly_pillar_inputs,
        chunks=[
            {"source": c.source, "section": c.section_title or c.section}
            for c in inputs.policy_chunks
        ],
    )
    prompt = _NARRATIVE_PROMPT.format(
        year=inputs.year,
        compare_to_year=inputs.compare_to_year,
        pillar_inputs_json=json.dumps(
            inputs.yearly_pillar_inputs,
            indent=2,
            default=lambda o: float(o) if hasattr(o, "__float__") else str(o),
        ),
    )
    try:
        section.narrative_md = _invoke_llm(prompt, "narrative")
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "yearly narrative failed (%s); using fallback",
            exc,
        )
        section.narrative_md = (
            "**Commercial.** _Narrative unavailable (LLM error)._\n\n"
            "**Claims.** _Narrative unavailable._\n\n"
            "**Customer.** _Narrative unavailable._\n\n"
            "**Compliance.** _Narrative unavailable._"
        )
    return section


_JSON_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def _parse_recommendation_list(raw: str) -> list[dict]:
    text = _JSON_FENCE.sub("", raw.strip()).strip()
    if not text.startswith("["):
        m = re.search(r"\[.*\]", text, re.DOTALL)
        if m:
            text = m.group(0)
    try:
        payload = json.loads(text)
        if isinstance(payload, list):
            return payload
    except json.JSONDecodeError:
        pass
    log.warning(
        "narrator: recommendations not parseable as JSON array: %r",
        raw[:160],
    )
    return []


def narrate_recommendations(
    inputs: CollectedInputs,
) -> RecommendationsSection:
    section = RecommendationsSection(items=[])
    prompt = _RECOMMENDATIONS_PROMPT.format(
        year=inputs.year,
        risk_indicators_json=json.dumps(
            _risk_payload(inputs.risk_indicators.indicators), indent=2,
        ),
        headline_metrics_json=json.dumps(
            inputs.headline_metrics, indent=2,
        ),
        policy_chunks_json=json.dumps(
            _chunks_to_payload(inputs.policy_chunks), indent=2,
        ),
    )
    try:
        raw = _invoke_llm(prompt, "recommendations")
    except Exception as exc:  # noqa: BLE001
        log.warning("recommendations narration failed: %s", exc)
        raw = "[]"

    items: list[Recommendation] = []
    for entry in _parse_recommendation_list(raw):
        if not isinstance(entry, dict):
            continue
        items.append(Recommendation(
            title=str(entry.get("title", "")).strip(),
            rationale_md=str(entry.get("rationale_md", "")).strip(),
            metric_anchor=str(entry.get("metric_anchor", "")).strip(),
            chunk_anchor=str(entry.get("chunk_anchor", "")).strip(),
        ))

    if not items:
        # Deterministic fallback: surface the amber/red risk
        # indicators as no-op 'investigate' recommendations so the
        # section is never empty.
        for ri in inputs.risk_indicators.indicators:
            if ri.severity == "green":
                continue
            items.append(Recommendation(
                title=f"Investigate {ri.label.lower()} "
                      f"({ri.severity})",
                rationale_md=(
                    f"{ri.label} is {ri.value_str}; "
                    f"threshold flag: {ri.severity}. {ri.note}"
                ),
                metric_anchor=ri.label,
                chunk_anchor="",
            ))

    section.items = items
    return section
