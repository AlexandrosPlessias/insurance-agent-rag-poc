"""RAG agent helpers, sync `rag_node`, and a thin `answer_question`.

each step (reformulate, retrieve, generate) gets its own span.
"""

import re
import time
from dataclasses import dataclass, field

from langchain_core.messages import HumanMessage, SystemMessage

from agentic_backend.agents.memory_agent import format_history_for_prompt
from agentic_backend.audit import events as audit_events
from agentic_backend.audit.middleware import record as audit_record
from agentic_backend.config import settings
from agentic_backend.graph.state import GraphState, is_fast_mode
from agentic_backend.llm import load_prompt
from agentic_backend.llm.ollama_client import get_fast_llm, get_llm
from agentic_backend.observability.logging import get_logger
from agentic_backend.observability.metrics import record_rag_chunks, track_node
from agentic_backend.observability.tracing import annotate_request_span, get_tracer
from agentic_backend.rag.retriever import RetrievedChunk, retrieve

log = get_logger(__name__)
tracer = get_tracer(__name__)

SYSTEM_PROMPT = load_prompt("rag")
REFORMULATE_PROMPT = load_prompt("reformulate")


@dataclass
class RagResponse:
    answer: str
    citations: list[RetrievedChunk] = field(default_factory=list)
    reformulated_query: str = ""
    validated: bool = True
    retry_count: int = 0
    route: str = ""


def reformulate_question(question: str, history: list[dict] | None = None) -> str:
    with tracer.start_as_current_span("rag.reformulate") as span:
        span.set_attribute("question.preview", question[:80])
        log.info("Reformulating: %r", question[:80])
        t0 = time.perf_counter()
        history_block = format_history_for_prompt(history or [], max_turns=2)
        if not history_block:
            # Standalone questions are usually explicit; skip a costly rewrite call.
            span.set_attribute("reformulate.skipped", True)
            log.info("  -> reformulation skipped (no prior history)")
            return question.strip()
        user_content = question
        if history_block:
            user_content = (
                f"{history_block}\n"
                f"Now rewrite this question, resolving references to the "
                f"conversation above when needed:\n{question}"
            )
        # Reformulation is a lightweight rewrite task; use the fast 3B model.
        result = get_fast_llm().invoke(
            [
                SystemMessage(content=REFORMULATE_PROMPT),
                HumanMessage(content=user_content),
            ]
        )
        rewritten = str(result.content).strip().strip('"').strip("'")
        span.set_attribute("reformulated.preview", (rewritten or question)[:100])
        log.info(
            "  -> reformulated in %.2fs: %r",
            time.perf_counter() - t0,
            rewritten[:100],
        )
        return rewritten or question


def _format_context(chunks: list[RetrievedChunk]) -> str:
    if not chunks:
        return "(no documents indexed)"
    max_chunks = 3
    max_chars_per_chunk = 700
    formatted_parts: list[str] = []
    for i, chunk in enumerate(chunks[:max_chunks]):
        content = (chunk.content or "").strip()
        if len(content) > max_chars_per_chunk:
            content = content[:max_chars_per_chunk].rstrip() + " ..."
        formatted_parts.append(f"[{i + 1}] {chunk.as_citation()}\n{content}")
    return "\n\n".join(formatted_parts)


def build_rag_prompt(
    chunks: list[RetrievedChunk],
    critique: str = "",
    history: list[dict] | None = None,
) -> str:
    prompt = SYSTEM_PROMPT.format(context=_format_context(chunks))
    history_block = format_history_for_prompt(history or [], max_turns=3)
    if history_block:
        prompt = f"{history_block}\n{prompt}"
    if critique:
        prompt += (
            "\n\nPREVIOUS ATTEMPT WAS REJECTED. Validator critique:\n"
            f"{critique}\n\n"
            "Address the critique in your new answer."
        )
    return prompt


def citation_payload(c: RetrievedChunk) -> dict:
    return {
        "source": c.source,
        "content": c.content,
        "download_url": f"/sources/{c.source}",
        "section": c.section,
        "section_title": c.section_title,
        "chunk_index": c.chunk_index,
    }


def _extract_refund_window_answer(question: str, chunks: list[RetrievedChunk]) -> str | None:
    """Return a fast extractive answer for refund-window questions when possible."""
    question_l = question.lower()
    if "refund" not in question_l or "window" not in question_l:
        return None

    patterns = [
        re.compile(r"refund window[^.\n]{0,120}?(\d{1,3})\s*days", re.IGNORECASE),
        re.compile(r"(\d{1,3})\s*days[^.\n]{0,120}?refund window", re.IGNORECASE),
    ]

    for chunk in chunks[:3]:
        content = (chunk.content or "").strip()
        if not content:
            continue
        for pattern in patterns:
            match = pattern.search(content)
            if match:
                days = match.group(1)
                return (
                    f"The refund window is {days} days from the date of purchase. "
                    f"(Source: {chunk.source})"
                )
    return None


def rag_node(state: GraphState) -> dict:
    """Sync RAG node used by the compiled LangGraph (non-streaming)."""
    question = state.get("question") or ""
    retry_count = state.get("retry_count", 0)
    critique = state.get("last_critique", "")
    history = state.get("history", [])
    target_year = state.get("target_year")
    where_filter = {"year": int(target_year)} if target_year is not None else None

    with tracer.start_as_current_span("rag.node") as span, track_node("rag", route="rag"):
        annotate_request_span(
            span,
            user_id=state.get("user_id"),
            conversation_id=state.get("conversation_id"),
        )
        span.set_attribute("rag.retry_count", retry_count)
        span.set_attribute("rag.has_critique", bool(critique))
        span.set_attribute("rag.history_msgs", len(history))
        if target_year is not None:
            span.set_attribute("rag.target_year", int(target_year))

        if retry_count == 0:
            log.info("RAG node (initial): %r", question[:80])
            reformulated = reformulate_question(question, history=history)
            chunks = retrieve(reformulated, where_filter=where_filter)
            record_rag_chunks(len(chunks))
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
        else:
            log.info(
                "RAG node (retry %d) - reusing previous retrieval",
                retry_count,
            )
            reformulated = state.get("reformulated_query", question)
            chunks = state.get("chunks", [])
        span.set_attribute("rag.chunk_count", len(chunks))

        if is_fast_mode(state):
            extracted = _extract_refund_window_answer(question, chunks)
            if extracted:
                log.info("  -> extractive shortcut used (refund-window)")
                return {
                    "reformulated_query": reformulated,
                    "chunks": chunks,
                    "draft_answer": extracted,
                }

        prompt = build_rag_prompt(chunks, critique=critique, history=history)
        messages = [
            SystemMessage(content=prompt),
            HumanMessage(content=question),
        ]
        log.info("Calling LLM with %d chunk(s) ...", len(chunks))
        with tracer.start_as_current_span("rag.llm.invoke") as llm_span:
            t0 = time.perf_counter()
            result = get_llm().invoke(messages)
            elapsed = time.perf_counter() - t0
            llm_span.set_attribute("llm.duration_s", round(elapsed, 3))
            llm_span.set_attribute("llm.answer_chars", len(str(result.content)))
        log.info("  -> LLM responded in %.2fs", elapsed)

        answer_text = str(result.content)
        audit_record(
            state,
            event_type=audit_events.RAG_ANSWER,
            payload={
                "retry_count": retry_count,
                "answer_chars": len(answer_text),
                "duration_s": round(elapsed, 3),
                "target_year": state.get("target_year"),
            },
        )

        return {
            "reformulated_query": reformulated,
            "chunks": chunks,
            "draft_answer": answer_text,
        }


def answer_question(
    question: str,
    user_id: str = "default_user",
    history: list[dict] | None = None,
    user_activity: list[dict] | None = None,
) -> RagResponse:
    """Run the full LangGraph and return a sync RagResponse."""
    from agentic_backend.graph.builder import get_graph  # lazy import (break cycle)

    initial: dict = {
        "question": question,
        "user_id": user_id,
        "history": history or [],
        "user_activity": user_activity or [],
    }
    state = get_graph().invoke(initial)
    raw_citations = state.get("final_citations") or state.get("chunks") or []
    citations = [RetrievedChunk(**c) if isinstance(c, dict) else c for c in raw_citations]
    return RagResponse(
        answer=state.get("final_answer", state.get("draft_answer", "")),
        citations=citations,
        reformulated_query=state.get("reformulated_query", ""),
        validated=state.get("validated", True),
        retry_count=state.get("retry_count", 0),
        route=state.get("route", ""),
    )
