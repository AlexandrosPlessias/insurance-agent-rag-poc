"""Retrieval pipeline returning chunks plus citation metadata."""
import time
from dataclasses import dataclass

from langchain_core.documents import Document

from agentic_backend.config import settings
from agentic_backend.observability.logging import get_logger
from agentic_backend.observability.tracing import get_tracer
from agentic_backend.rag.vectorstore import get_vectorstore

log = get_logger(__name__)
tracer = get_tracer(__name__)


@dataclass
class RetrievedChunk:
    content: str
    source: str
    section: str = ""
    section_title: str = ""
    chunk_index: int = 0   # per-source 1-based index

    def as_citation(self) -> str:
        topic = self.section_title or self.section
        if topic:
            return f"{self.source}  -  {topic}"
        return self.source


def retrieve(
    query: str,
    k: int | None = None,
    *,
    where_filter: dict | None = None,
) -> list[RetrievedChunk]:
    """Top-k semantic search with optional Chroma metadata filter.

    `where_filter` is forwarded verbatim to Chroma's `filter=` kwarg
    (e.g. `{"year": 2020}`). Used to scope retrieval to a
    specific policy year.
    """
    k = k or settings.retrieval_k
    with tracer.start_as_current_span("rag.retrieve") as span:
        span.set_attribute("retrieve.k", k)
        span.set_attribute("retrieve.query_preview", query[:80])
        if where_filter:
            span.set_attribute(
                "retrieve.where_filter", str(where_filter)
            )
            log.info(
                "Retrieving top-%d for query: %r (filter=%s)",
                k,
                query[:80],
                where_filter,
            )
        else:
            log.info("Retrieving top-%d for query: %r", k, query[:80])
        t0 = time.perf_counter()
        docs: list[Document] = get_vectorstore().similarity_search(
            query, k=k, filter=where_filter
        )
        elapsed = time.perf_counter() - t0
        span.set_attribute("retrieve.result_count", len(docs))
        span.set_attribute("retrieve.duration_s", round(elapsed, 3))
        log.info(
            "  -> retrieved %d chunks in %.2fs", len(docs), elapsed
        )
        return [
            RetrievedChunk(
                content=d.page_content,
                source=d.metadata.get("source", "unknown"),
                section=str(d.metadata.get("section", "") or ""),
                section_title=str(
                    d.metadata.get("section_title", "") or ""
                ),
                chunk_index=int(d.metadata.get("chunk_index") or 0),
            )
            for d in docs
        ]
