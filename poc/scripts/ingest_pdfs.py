"""Ingest PDFs from data/raw/ into ChromaDB (Phase 1).

Run from poc/:  python scripts/ingest_pdfs.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402
from app.observability.logging import (  # noqa: E402
    configure_logging,
    get_logger,
)
from app.rag.chunker import chunk_documents  # noqa: E402
from app.rag.loader import load_pdfs  # noqa: E402
from app.rag.vectorstore import add_documents  # noqa: E402

configure_logging()
log = get_logger("ingest_pdfs")


def main() -> int:
    raw_dir = settings.raw_pdf_dir
    if not raw_dir.exists():
        log.error("No raw PDF directory at %s", raw_dir)
        return 1

    log.info("=" * 60)
    log.info("Ingestion pipeline starting")
    log.info("  raw_dir     = %s", raw_dir)
    log.info("  chroma_dir  = %s", settings.chroma_persist_dir)
    log.info("  collection  = %s", settings.chroma_collection)
    log.info("  embed_model = %s", settings.embed_model)
    log.info("=" * 60)

    documents = load_pdfs(raw_dir)
    if not documents:
        log.warning(
            "No PDFs found in %s. Drop *.pdf files there and re-run.",
            raw_dir,
        )
        return 0

    chunks = chunk_documents(documents)
    add_documents(chunks)
    log.info("Ingestion complete. Total chunks indexed: %d", len(chunks))
    return 0


if __name__ == "__main__":
    sys.exit(main())
