"""Text splitting that preserves page-number metadata for citations."""
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.config import settings
from app.observability.logging import get_logger

log = get_logger(__name__)


def chunk_documents(documents: list[Document]) -> list[Document]:
    log.info(
        "Chunking %d pages (size=%d, overlap=%d) ...",
        len(documents),
        settings.chunk_size,
        settings.chunk_overlap,
    )
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    chunks = splitter.split_documents(documents)
    log.info("  → produced %d chunks", len(chunks))
    return chunks
