"""Report agent (Phase 3+4+5)."""
import json
import re
import time

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.memory_agent import format_user_activity
from app.audit import events as audit_events
from app.audit.middleware import record as audit_record
from app.graph.state import GraphState
from app.llm import load_prompt
from app.llm.ollama_client import get_llm
from app.observability.logging import get_logger
from app.observability.metrics import record_rag_chunks, track_node
from app.observability.tracing import annotate_request_span, get_tracer
from app.rag.retriever import RetrievedChunk, retrieve
from app.reporting.charts import render_premium_chart
from app.reporting.markdown import build_policy_report

log = get_logger(__name__)
tracer = get_tracer(__name__)

EXTRACT_PROMPT = load_prompt("report_extract")
REPORT_K = 10


def _format_context(chunks: list[RetrievedChunk]) -> str:
    return "\n\n".join(
        f"[{i + 1}] {c.as_citation()}\n{c.content}"
        for i, c in enumerate(chunks)
    )


def _parse_json_fallback(raw: str) -> dict:
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
    log.warning("Report extraction not parseable as JSON: %r", raw[:120])
    return {}


def _extract_policy_data(chunks: list[RetrievedChunk]) -> dict:
    with tracer.start_as_current_span("report.extract") as span:
        log.info(
            "Extracting structured policy data from %d chunks ...",
            len(chunks),
        )
        t0 = time.perf_counter()
        result = get_llm().invoke(
            [
                SystemMessage(content=EXTRACT_PROMPT),
                HumanMessage(
                    content=f"POLICY CONTEXT:\n{_format_context(chunks)}"
                ),
            ]
        )
        parsed = _parse_json_fallback(str(result.content))
        elapsed = time.perf_counter() - t0
        span.set_attribute("report.extract_keys", len(parsed))
        span.set_attribute("report.extract_duration_s", round(elapsed, 3))
        log.info(
            "  -> extracted %d top-level keys in %.2fs",
            len(parsed),
            elapsed,
        )
        return parsed


def report_node(state: GraphState) -> dict:
    """Build a Markdown policy report. Skips validation."""
    question = state.get("question") or ""
    user_activity = state.get("user_activity", []) or []

    with tracer.start_as_current_span("report.node") as span, \
            track_node("report", route="report"):
        annotate_request_span(
            span,
            user_id=state.get("user_id"),
            conversation_id=state.get("conversation_id"),
        )
        span.set_attribute("question.preview", question[:80])
        span.set_attribute("report.user_activity_items", len(user_activity))
        log.info(
            "Report agent invoked: %r (user_activity=%d items)",
            question[:80],
            len(user_activity),
        )
        t_total = time.perf_counter()

        target_year = state.get("target_year")
        where_filter = (
            {"year": int(target_year)} if target_year is not None else None
        )
        if target_year is not None:
            span.set_attribute("report.target_year", int(target_year))
        chunks = retrieve(question, k=REPORT_K, where_filter=where_filter)
        span.set_attribute("report.chunk_count", len(chunks))
        record_rag_chunks(len(chunks), route="report")
        if not chunks:
            log.warning("Report: no chunks retrieved")
            markdown = (
                "# Policy Summary Report\n\n"
                "No indexed documents to summarise. "
                "Ingest a policy PDF first via "
                "`python scripts/ingest_pdfs.py`."
            )
            return {
                "chunks": [],
                "draft_answer": markdown,
                "final_answer": markdown,
                "final_citations": [],
                "validated": True,
                "retry_count": 0,
            }

        data = _extract_policy_data(chunks)
        chart_b64 = render_premium_chart(data)
        activity_bullets = format_user_activity(user_activity)
        markdown = build_policy_report(
            data,
            chunks,
            chart_b64=chart_b64,
            user_activity_bullets=activity_bullets,
        )

        span.set_attribute("report.chart_present", bool(chart_b64))
        span.set_attribute("report.markdown_chars", len(markdown))
        log.info(
            "Report done: %.2fs total, %d-char markdown, "
            "chart=%s, activity_items=%d",
            time.perf_counter() - t_total,
            len(markdown),
            "yes" if chart_b64 else "no",
            len(activity_bullets),
        )

        audit_record(
            state,
            event_type=audit_events.REPORT_GENERATE,
            payload={
                "target_year": target_year,
                "chunk_count": len(chunks),
                "chart_present": bool(chart_b64),
                "markdown_chars": len(markdown),
                "sources": sorted({c.source for c in chunks if c.source}),
            },
        )
        return {
            "chunks": chunks,
            "draft_answer": markdown,
            "final_answer": markdown,
            "final_citations": chunks,
            "validated": True,
            "retry_count": 0,
        }
