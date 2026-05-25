"""Retrieval pipeline returning chunks plus citation metadata."""
from dataclasses import dataclass

from langchain_core.documents import Document

from app.config import settings
from app.rag.vectorstore import get_vectorstore


@dataclass
class RetrievedChunk:
    content: str
    source: str
    page: int

    def as_citation(self) -> str:
        return f"{self.source} (p. {self.page})"


def retrieve(query: str, k: int | None = None) -> list[RetrievedChunk]:
    docs: list[Document] = get_vectorstore().similarity_search(
        query, k=k or settings.retrieval_k
    )
    return [
        RetrievedChunk(
            content=d.page_content,
            source=d.metadata.get("source", "unknown"),
            page=int(d.metadata.get("page", 0)),
        )
        for d in docs
    ]
