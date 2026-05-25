"""ChromaDB initialisation, persistence, and collection helpers."""
from langchain_chroma import Chroma
from langchain_core.documents import Document

from app.config import settings
from app.llm.ollama_client import get_embeddings


def get_vectorstore() -> Chroma:
    settings.chroma_persist_dir.mkdir(parents=True, exist_ok=True)
    return Chroma(
        collection_name=settings.chroma_collection,
        embedding_function=get_embeddings(),
        persist_directory=str(settings.chroma_persist_dir),
    )


def add_documents(documents: list[Document]) -> int:
    if not documents:
        return 0
    get_vectorstore().add_documents(documents)
    return len(documents)


def reset_collection() -> None:
    """Delete every vector from the collection (keeps the persist directory)."""
    vs = get_vectorstore()
    vs.delete_collection()
