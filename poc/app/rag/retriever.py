"""Retrieval pipeline returning chunks plus citation metadata."""
import time
from dataclasses import dataclass

from langchain_core.documents import Document

from app.config import settings
from app.observability.logging import get_logger
from app.rag.vectorstore import get_vectorstore

log = get_logger(__name__)


@dataclass
class RetrievedChunk:
    content: str
    source: str
    page: int

    def as_citation(self) -> str:
        return f"{self.source} (p. {self.page})"


def retrieve(query: str, k: int | None = None) -> list[RetrievedChunk]:
    k = k or settings.retrieval_k
    log.info("Retrieving top-%d for query: %r", k, query[:80])
    t0 = time.perf_counter()
    docs: list[Document] = get_vectorstore().similarity_search(query, k=k)
    log.info("  → retrieved %d chunks in %.2fs", len(docs), time.perf_counter() - t0)
    return [
        RetrievedChunk(
            content=d.page_content,
            source=d.metadata.get("source", "unknown"),
            page=int(d.metadata.get("page", 0)),
        )
        for d in docs
    ]
