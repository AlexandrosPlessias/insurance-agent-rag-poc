"""Reset ChromaDB collection. For database reset run:
  docker compose exec postgres psql -U poc -d poc < src/scripts/sql/reset_stores.sql
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agentic_backend.config import settings
from agentic_backend.observability.logging import configure_logging, get_logger
from agentic_backend.rag.vectorstore import reset_collection

configure_logging()
log = get_logger("reset_stores")


def main() -> int:
    log.info("Resetting ChromaDB collection via %s:%s", settings.chroma_host, settings.chroma_port)
    try:
        reset_collection()
        log.info("ChromaDB reset complete. Raw PDFs in %s are kept.", settings.raw_pdf_dir)
    except Exception as exc:
        log.warning("ChromaDB reset failed (server may be down): %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
