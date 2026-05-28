"""ChromaDB initialisation, persistence, and collection helpers."""
import time

from langchain_chroma import Chroma
from langchain_core.documents import Document

from app.config import settings
from app.llm.ollama_client import get_embeddings
from app.observability.logging import get_logger
from app.observability.tracing import get_tracer

log = get_logger(__name__)
tracer = get_tracer(__name__)


def get_vectorstore() -> Chroma:
    settings.chroma_persist_dir.mkdir(parents=True, exist_ok=True)
    return Chroma(
        collection_name=settings.chroma_collection,
        embedding_function=get_embeddings(),
        persist_directory=str(settings.chroma_persist_dir),
    )


def add_documents(documents: list[Document]) -> int:
    if not documents:
        log.warning("add_documents called with empty list")
        return 0
    with tracer.start_as_current_span("vectorstore.add_documents") as span:
        span.set_attribute("vectorstore.chunks", len(documents))
        log.info("Embedding + indexing %d chunks ...", len(documents))
        t0 = time.perf_counter()
        get_vectorstore().add_documents(documents)
        elapsed = time.perf_counter() - t0
        span.set_attribute("vectorstore.duration_s", round(elapsed, 3))
        log.info(
            "  -> indexed %d chunks in %.2fs",
            len(documents),
            elapsed,
        )
        return len(documents)


def reset_collection() -> None:
    """Delete every vector from the collection."""
    log.info("Resetting Chroma collection: %s", settings.chroma_collection)
    get_vectorstore().delete_collection()


def delete_by_source(source: str) -> int:
    """Remove every chunk whose metadata `source == filename`.

    Returns the number of chunks deleted. Idempotent: zero-match is OK.
    Used by the ingestion pipeline to keep re-ingest of the same PDF
    from inserting duplicate rows.
    """
    if not source:
        return 0
    with tracer.start_as_current_span("vectorstore.delete_by_source") as span:
        span.set_attribute("vectorstore.source", source)
        collection = get_vectorstore()._collection
        try:
            existing = collection.get(where={"source": source}, include=[])
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "delete_by_source query failed for %r: %s", source, exc
            )
            span.set_attribute("vectorstore.removed", 0)
            return 0
        ids = existing.get("ids") or []
        if not ids:
            span.set_attribute("vectorstore.removed", 0)
            return 0
        try:
            collection.delete(ids=ids)
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "delete_by_source delete failed for %r: %s", source, exc
            )
            span.set_attribute("vectorstore.removed", 0)
            return 0
        span.set_attribute("vectorstore.removed", len(ids))
        log.info(
            "Removed %d existing chunks for source=%r", len(ids), source
        )
        return len(ids)
