"""RAG worker agent — retrieval-augmented answering over policy docs."""
import time
from dataclasses import dataclass

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


@dataclass
class RagResponse:
    answer: str
    citations: list[RetrievedChunk]


def answer_question(question: str) -> RagResponse:
    log.info("RAG agent invoked: %r", question[:80])
    t_total = time.perf_counter()

    chunks = retrieve(question)
    context = "\n\n".join(
        f"[{i + 1}] {c.as_citation()}\n{c.content}"
        for i, c in enumerate(chunks)
    )
    if not chunks:
        log.warning("No chunks retrieved - answer will be unsupported")

    prompt = SYSTEM_PROMPT.format(
        context=context or "(no documents indexed)"
    )
    messages = [
        SystemMessage(content=prompt),
        HumanMessage(content=question),
    ]

    log.info("Calling LLM with %d context chunk(s) ...", len(chunks))
    t_llm = time.perf_counter()
    result = get_llm().invoke(messages)
    log.info("  -> LLM responded in %.2fs", time.perf_counter() - t_llm)

    answer = str(result.content)
    log.info(
        "RAG done: %.2fs total, %d citations, %d-char answer",
        time.perf_counter() - t_total,
        len(chunks),
        len(answer),
    )
    return RagResponse(answer=answer, citations=chunks)
