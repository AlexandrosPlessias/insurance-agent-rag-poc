"""Wipe ChromaDB collection, memory SQLite, and Phase 7 audit SQLite.

ChromaDB runs in server mode (Docker) — the collection is deleted via the
HTTP API. Raw PDFs in data/knowledge_base/raw/ are kept. Use --keep-audit to
preserve the audit trail across resets (useful when iterating on retrieval
while keeping the compliance log intact).

Run from inside the docker compose network or with ChromaDB port exposed:
  python scripts/reset_stores.py               # wipe chroma + memory + audit
  python scripts/reset_stores.py --keep-audit  # keep audit.sqlite
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agentic_backend.config import settings  # noqa: E402
from agentic_backend.observability.logging import configure_logging, get_logger  # noqa: E402
from agentic_backend.rag.vectorstore import reset_collection  # noqa: E402

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

    log.info("Resetting ChromaDB collection via %s:%s", settings.chroma_host, settings.chroma_port)
    try:
        reset_collection()
    except Exception as exc:
        log.warning("ChromaDB reset failed (server may be down): %s", exc)

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
