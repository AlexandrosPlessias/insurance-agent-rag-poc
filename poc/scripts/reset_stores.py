"""Wipe local ChromaDB, memory SQLite, and Phase 7 audit SQLite.

Raw PDFs in data/knowledge_base/raw/ are kept. Use --keep-audit to
preserve the audit trail across resets (useful when iterating on
retrieval while keeping the compliance log intact).

Run from poc/:
  python scripts/reset_stores.py               # wipe chroma + memory + audit
  python scripts/reset_stores.py --keep-audit  # keep audit.sqlite
"""
import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402
from app.observability.logging import configure_logging, get_logger  # noqa: E402

configure_logging()
log = get_logger("reset_stores")


def _unlink(path: Path, label: str) -> None:
    if path.exists():
        log.info("Removing %s (%s)", path, label)
        path.unlink()
    else:
        log.info("%s not present: %s", label, path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--keep-audit",
        action="store_true",
        help="Do not delete the Phase 7 audit.sqlite file.",
    )
    args = parser.parse_args()

    if settings.chroma_persist_dir.exists():
        log.info("Removing %s", settings.chroma_persist_dir)
        shutil.rmtree(settings.chroma_persist_dir)
    else:
        log.info("ChromaDB dir not present: %s", settings.chroma_persist_dir)

    _unlink(settings.sqlite_path, "memory SQLite")

    if args.keep_audit:
        log.info(
            "Keeping audit DB at %s (--keep-audit)",
            settings.audit_sqlite_path,
        )
    else:
        _unlink(settings.audit_sqlite_path, "audit SQLite")

    log.info("Done. Raw PDFs in %s are kept.", settings.raw_pdf_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
