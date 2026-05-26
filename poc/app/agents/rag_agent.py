"""RAG agent helpers, sync `rag_node`, and a thin `answer_question`.

Consumers:
  - app/graph/builder.py: imports rag_node for the compiled graph.
  - app/graph/streaming.py: imports reformulate_question, build_rag_prompt,
    citation_payload to drive the streaming walker.
  - smoke_test.py: imports answer_question for end-to-end demos.
"""
import time
from dataclasses import dataclass, field

from langchain_core.messages import HumanMessage, SystemMessage

from app.graph.state import GraphState
from app.llm import load_prompt
from app.llm.ollama_client import get_llm
from app.observability.logging import get_logger
from app.rag.retriever import RetrievedChunk, retrieve

log = get_logger(__name__)

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


def reformulate_question(question: str) -> str:
    log.info("Reformulating: %r", question[:80])
    t0 = time.perf_counter()
    result = get_llm().invoke(
        [
            SystemMessage(content=REFORMULATE_PROMPT),
            HumanMessage(content=question),
        ]
    )
    rewritten = str(result.content).strip().strip('"').strip("'")
    log.info(
        "  -> reformulated in %.2fs: %r",
        time.perf_counter() - t0,
        rewritten[:100],
    )
    return rewritten or question


def _format_context(chunks: list[RetrievedChunk]) -> str:
    if not chunks:
        return "(no documents indexed)"
    return "\n\n".join(
        f"[{i + 1}] {c.as_citation()}\n{c.content}"
        for i, c in enumerate(chunks)
    )


def build_rag_prompt(
    chunks: list[RetrievedChunk],
    critique: str = "",
) -> str:
    prompt = SYSTEM_PROMPT.format(context=_format_context(chunks))
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
        "page": c.page,
        "content": c.content,
        "download_url": f"/sources/{c.source}",
    }


def rag_node(state: GraphState) -> dict:
    """Sync RAG node used by the compiled LangGraph (non-streaming)."""
    question = state["question"]
    retry_count = state.get("retry_count", 0)
    critique = state.get("last_critique", "")

    if retry_count == 0:
        log.info("RAG node (initial): %r", question[:80])
        reformulated = reformulate_question(question)
        chunks = retrieve(reformulated)
    else:
        log.info(
            "RAG node (retry %d) - reusing previous retrieval",
            retry_count,
        )
        reformulated = state.get("reformulated_query", question)
        chunks = state.get("chunks", [])

    prompt = build_rag_prompt(chunks, critique=critique)
    messages = [
        SystemMessage(content=prompt),
        HumanMessage(content=question),
    ]
    log.info("Calling LLM with %d chunk(s) ...", len(chunks))
    t0 = time.perf_counter()
    result = get_llm().invoke(messages)
    log.info("  -> LLM responded in %.2fs", time.perf_counter() - t0)

    return {
        "reformulated_query": reformulated,
        "chunks": chunks,
        "draft_answer": str(result.content),
    }


def answer_question(question: str) -> RagResponse:
    """Run the full LangGraph and return a sync RagResponse."""
    from app.graph.builder import get_graph  # lazy import (break cycle)

    state = get_graph().invoke({"question": question})
    return RagResponse(
        answer=state.get("final_answer", state.get("draft_answer", "")),
        citations=state.get("final_citations")
        or state.get("chunks")
        or [],
        reformulated_query=state.get("reformulated_query", ""),
        validated=state.get("validated", True),
        retry_count=state.get("retry_count", 0),
        route=state.get("route", ""),
    )
