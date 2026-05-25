"""Ingest PDFs from data/raw/ into ChromaDB (Phase 1)."""
import sys
from pathlib import Path

# Allow running this script directly: `python scripts/ingest_pdfs.py`
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402
from app.rag.chunker import chunk_documents  # noqa: E402
from app.rag.loader import load_pdfs  # noqa: E402
from app.rag.vectorstore import add_documents  # noqa: E402


def main() -> int:
    raw_dir = settings.raw_pdf_dir
    if not raw_dir.exists():
        print(f"No raw PDF directory at {raw_dir}.", file=sys.stderr)
        return 1

    print(f"Loading PDFs from {raw_dir} ...")
    documents = load_pdfs(raw_dir)
    if not documents:
        print(f"No PDFs found in {raw_dir}. Drop *.pdf files there and re-run.")
        return 0

    print(f"Loaded {len(documents)} pages. Chunking ...")
    chunks = chunk_documents(documents)
    print(f"Produced {len(chunks)} chunks. Embedding + indexing ...")

    n = add_documents(chunks)
    print(f"Indexed {n} chunks into ChromaDB at {settings.chroma_persist_dir}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
