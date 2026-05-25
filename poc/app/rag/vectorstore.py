"""ChromaDB initialisation, persistence, and collection helpers."""
import time

from langchain_chroma import Chroma
from langchain_core.documents import Document

from app.config import settings
from app.llm.ollama_client import get_embeddings
from app.observability.logging import get_logger

log = get_logger(__name__)


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
    log.info("Embedding + indexing %d chunks ...", len(documents))
    t0 = time.perf_counter()
    get_vectorstore().add_documents(documents)
    log.info(
        "  -> indexed %d chunks in %.2fs",
        len(documents),
        time.perf_counter() - t0,
    )
    return len(documents)


def reset_collection() -> None:
    """Delete every vector from the collection."""
    log.info("Resetting Chroma collection: %s", settings.chroma_collection)
    get_vectorstore().delete_collection()
