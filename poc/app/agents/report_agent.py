"""Report agent (Phase 3).

Pipeline:
  1. retrieve(question, k=10) - wide context for structured extraction.
  2. LLM extracts a JSON object of policy fields.
  3. reporting.charts renders a matplotlib chart -> base64 PNG.
  4. reporting.markdown stitches everything into a Markdown report.
"""
import json
import re
import time

from langchain_core.messages import HumanMessage, SystemMessage

from app.graph.state import GraphState
from app.llm import load_prompt
from app.llm.ollama_client import get_llm
from app.observability.logging import get_logger
from app.rag.retriever import RetrievedChunk, retrieve
from app.reporting.charts import render_premium_chart
from app.reporting.markdown import build_policy_report

log = get_logger(__name__)

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
    log.info(
        "Extracting structured policy data from %d chunks ...",
        len(chunks),
    )
    t0 = time.perf_counter()
    result = get_llm().invoke(
        [
            SystemMessage(content=EXTRACT_PROMPT),
            HumanMessage(content=f"POLICY CONTEXT:\n{_format_context(chunks)}"),
        ]
    )
    parsed = _parse_json_fallback(str(result.content))
    log.info(
        "  -> extracted %d top-level keys in %.2fs",
        len(parsed),
        time.perf_counter() - t0,
    )
    return parsed


def report_node(state: GraphState) -> dict:
    """Build a Markdown policy report. Skips validation."""
    question = state["question"]
    log.info("Report agent invoked: %r", question[:80])
    t_total = time.perf_counter()

    chunks = retrieve(question, k=REPORT_K)
    if not chunks:
        log.warning("Report: no chunks retrieved")
        markdown = (
            "# Policy Summary Report\n\n"
            "No indexed documents to summarise. "
            "Ingest a policy PDF first via `python scripts/ingest_pdfs.py`."
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
    markdown = build_policy_report(data, chunks, chart_b64=chart_b64)

    log.info(
        "Report done: %.2fs total, %d-char markdown, chart=%s",
        time.perf_counter() - t_total,
        len(markdown),
        "yes" if chart_b64 else "no",
    )
    return {
        "chunks": chunks,
        "draft_answer": markdown,
        "final_answer": markdown,
        "final_citations": chunks,
        "validated": True,  # reports bypass the validator in Phase 3
        "retry_count": 0,
    }
