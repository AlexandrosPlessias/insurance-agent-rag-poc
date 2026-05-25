"""RAG worker agent - retrieval-augmented answering over policy docs.

Pipeline:
  1. reformulate_question() rewrites the user query for better retrieval.
  2. retrieve() pulls top-k chunks from ChromaDB.
  3. The LLM answers, grounded in those chunks (streaming or sync).
"""
import time
from dataclasses import dataclass
from typing import Iterator

from langchain_core.messages import HumanMessage, SystemMessage

from app.llm.ollama_client import get_llm
from app.observability.logging import get_logger
from app.rag.retriever import RetrievedChunk, retrieve

log = get_logger(__name__)

SYSTEM_PROMPT = (
    "You are an enterprise insurance assistant. "
    "Answer the user's question strictly using the provided context. "
    "If the context does not contain the answer, say so explicitly "
    "- do not invent information. "
    "Cite the source documents and page numbers you used.\n\n"
    "Context:\n{context}\n"
)

REFORMULATE_PROMPT = (
    "Rewrite the following user question to be optimal for retrieval "
    "from an insurance-policy knowledge base. Expand abbreviations, "
    "add domain terms, keep it concise (one sentence). "
    "Respond with ONLY the rewritten question - no preamble, no quotes."
)


@dataclass
class RagResponse:
    answer: str
    citations: list[RetrievedChunk]
    reformulated_query: str


def reformulate_question(question: str) -> str:
    log.info("Reformulating: %r", question[:80])
    t0 = time.perf_counter()
    messages = [
        SystemMessage(content=REFORMULATE_PROMPT),
        HumanMessage(content=question),
    ]
    result = get_llm().invoke(messages)
    rewritten = str(result.content).strip().strip('"').strip("'")
    log.info(
        "  -> reformulated in %.2fs: %r",
        time.perf_counter() - t0,
        rewritten[:100],
    )
    return rewritten or question


def _build_prompt(chunks: list[RetrievedChunk]) -> str:
    if not chunks:
        return SYSTEM_PROMPT.format(context="(no documents indexed)")
    context = "\n\n".join(
        f"[{i + 1}] {c.as_citation()}\n{c.content}"
        for i, c in enumerate(chunks)
    )
    return SYSTEM_PROMPT.format(context=context)


def _citation_payload(c: RetrievedChunk) -> dict:
    return {
        "source": c.source,
        "page": c.page,
        "content": c.content,
        "download_url": f"/sources/{c.source}",
    }


def answer_question(question: str) -> RagResponse:
    """Non-streaming variant - returns full answer at once."""
    log.info("RAG (sync): %r", question[:80])
    t_total = time.perf_counter()

    reformulated = reformulate_question(question)
    chunks = retrieve(reformulated)
    messages = [
        SystemMessage(content=_build_prompt(chunks)),
        HumanMessage(content=question),
    ]
    log.info("Calling LLM with %d context chunk(s) ...", len(chunks))
    t_llm = time.perf_counter()
    result = get_llm().invoke(messages)
    log.info("  -> LLM responded in %.2fs", time.perf_counter() - t_llm)

    log.info(
        "RAG sync done: %.2fs total",
        time.perf_counter() - t_total,
    )
    return RagResponse(
        answer=str(result.content),
        citations=chunks,
        reformulated_query=reformulated,
    )


def answer_question_stream(question: str) -> Iterator[dict]:
    """Streaming variant - yields event dicts.

    Event types:
      - {"type": "meta", "reformulated_query": str}
      - {"type": "token", "value": str}
      - {"type": "done",  "citations": list[dict]}
      - {"type": "error", "value": str}
    """
    log.info("RAG (stream): %r", question[:80])
    t_total = time.perf_counter()

    try:
        reformulated = reformulate_question(question)
        yield {"type": "meta", "reformulated_query": reformulated}

        chunks = retrieve(reformulated)
        if not chunks:
            log.warning("No chunks retrieved")

        messages = [
            SystemMessage(content=_build_prompt(chunks)),
            HumanMessage(content=question),
        ]
        log.info("Streaming LLM with %d chunk(s) ...", len(chunks))
        t_llm = time.perf_counter()
        n_events = 0
        for piece in get_llm().stream(messages):
            text = getattr(piece, "content", "")
            if text:
                n_events += 1
                yield {"type": "token", "value": str(text)}
        log.info(
            "  -> streamed %d events in %.2fs",
            n_events,
            time.perf_counter() - t_llm,
        )

        yield {
            "type": "done",
            "citations": [_citation_payload(c) for c in chunks],
        }
        log.info(
            "RAG stream done: %.2fs total",
            time.perf_counter() - t_total,
        )
    except Exception as exc:  # noqa: BLE001
        log.exception("RAG stream error")
        yield {"type": "error", "value": str(exc)}
