"""Bulk-ingest PDFs from data/knowledge_base/raw/ into ChromaDB (Phase 6).

For each PDF (in parallel):
  raw/<name>.pdf  ->  processed/<stem>.md   (markdown via pymupdf4llm)
                  ->  metadata/<stem>.json  (sidecar validated against schema)
                  ->  ChromaDB collection   (chunks with rich metadata)

The summariser LLM call dominates the per-doc cost. Ollama serves
`OLLAMA_NUM_PARALLEL` requests concurrently (default 4 in recent
versions), so we run that many ingestion workers by default. Override
with INGEST_WORKERS=N.

Run from poc/:  python scripts/ingest_pdfs.py
"""
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402
from app.ingestion.pipeline import ingest_document  # noqa: E402
from app.observability.logging import (  # noqa: E402
    configure_logging,
    get_logger,
)
from app.observability.tracing import setup_otel  # noqa: E402

configure_logging()
# Emit traces / logs to Aspire when OTEL_ENABLED=true. No-op otherwise,
# so the CLI works the same as before when observability is off.
setup_otel(service_suffix="ingest")
log = get_logger("ingest_pdfs")

DEFAULT_WORKERS = int(os.getenv("INGEST_WORKERS", "4"))


def main() -> int:
    raw_dir = settings.raw_pdf_dir
    if not raw_dir.exists():
        log.error("No raw PDF directory at %s", raw_dir)
        return 1

    pdfs = sorted(raw_dir.glob("*.pdf"))
    workers = max(1, min(DEFAULT_WORKERS, len(pdfs))) if pdfs else 1

    log.info("=" * 60)
    log.info("Phase 6 knowledge ingestion")
    log.info("  raw_dir      = %s", raw_dir)
    log.info("  processed    = %s", settings.processed_dir)
    log.info("  metadata     = %s", settings.metadata_dir)
    log.info("  chroma       = %s", settings.chroma_persist_dir)
    log.info("  pdf count    = %d", len(pdfs))
    log.info("  workers      = %d", workers)
    log.info("=" * 60)

    if not pdfs:
        log.warning(
            "No PDFs in %s. Drop *.pdf there and re-run.", raw_dir
        )
        return 0

    t0 = time.perf_counter()
    total_chunks = 0
    failures: list[str] = []

    if workers == 1:
        # Sequential path - keeps logs readable for single-PDF runs.
        for pdf in pdfs:
            try:
                result = ingest_document(pdf)
                total_chunks += result.chunks_indexed
            except Exception as exc:  # noqa: BLE001
                log.exception("Failed to ingest %s: %s", pdf.name, exc)
                failures.append(pdf.name)
    else:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = {
                ex.submit(ingest_document, pdf): pdf for pdf in pdfs
            }
            for future in as_completed(futures):
                pdf = futures[future]
                try:
                    result = future.result()
                    total_chunks += result.chunks_indexed
                    log.info(
                        "  OK: %s -> %d chunks in %.1fs",
                        pdf.name,
                        result.chunks_indexed,
                        result.duration_s,
                    )
                except Exception as exc:  # noqa: BLE001
                    log.exception(
                        "Failed to ingest %s: %s", pdf.name, exc
                    )
                    failures.append(pdf.name)

    elapsed = time.perf_counter() - t0
    log.info("=" * 60)
    log.info(
        "Ingestion done: %d PDFs, %d chunks, %.1fs wall time",
        len(pdfs) - len(failures),
        total_chunks,
        elapsed,
    )
    if failures:
        log.warning("Failed: %s", ", ".join(failures))
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
