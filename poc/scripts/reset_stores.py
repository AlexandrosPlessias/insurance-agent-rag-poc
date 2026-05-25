"""Wipe local ChromaDB and SQLite stores. Raw PDFs in data/raw/ are kept.

Run from poc/:  python scripts/reset_stores.py
"""
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402
from app.observability.logging import configure_logging, get_logger  # noqa: E402

configure_logging()
log = get_logger("reset_stores")


def main() -> int:
    if settings.chroma_persist_dir.exists():
        log.info("Removing %s", settings.chroma_persist_dir)
        shutil.rmtree(settings.chroma_persist_dir)
    else:
        log.info("ChromaDB dir not present: %s", settings.chroma_persist_dir)

    if settings.sqlite_path.exists():
        log.info("Removing %s", settings.sqlite_path)
        settings.sqlite_path.unlink()
    else:
        log.info("SQLite file not present: %s", settings.sqlite_path)

    log.info("Done. Raw PDFs in %s are kept.", settings.raw_pdf_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
