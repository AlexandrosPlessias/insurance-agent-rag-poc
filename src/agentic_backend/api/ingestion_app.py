"""Minimal FastAPI entrypoint for the ingestion-service pod.

Mounts only the /ingest and /sources routes — no LangGraph required.
On startup: clears ChromaDB and re-indexes all PDFs from the knowledge base.
"""
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agentic_backend.api.routes import ingest, sources
from agentic_backend.observability.logging import get_logger
from agentic_backend.observability.tracing import setup_otel

log = get_logger(__name__)


async def _startup_ingest() -> None:
    from agentic_backend.config import settings
    from agentic_backend.ingestion.pipeline import ingest_document
    from agentic_backend.rag.vectorstore import get_chunk_count, reset_collection

    raw_dir = settings.raw_pdf_dir
    if not raw_dir.exists():
        log.warning("No raw PDF dir at %s — skipping startup ingestion", raw_dir)
        return

    pdfs = sorted(raw_dir.glob("*.pdf"))
    if not pdfs:
        log.info("No PDFs found in %s — skipping startup ingestion", raw_dir)
        return

    # Skip re-indexing when data already exists — avoids wiping ChromaDB on
    # every `docker compose up` during development. Set FORCE_REINGEST=true
    # in src/.env to force a full wipe + re-index.
    try:
        existing_count = get_chunk_count()
    except Exception:
        existing_count = 0

    if existing_count > 0 and not settings.force_reingest:
        log.info(
            "=" * 60,
        )
        log.info(
            "STARTUP INGESTION SKIPPED — ChromaDB already has %d chunks.",
            existing_count,
        )
        log.info(
            "Set FORCE_REINGEST=true in src/.env and restart to force a full re-index.",
        )
        log.info("=" * 60)
        return

    log.info("=" * 60)
    log.info("STARTUP INGESTION — clearing ChromaDB + re-indexing %d PDF(s)", len(pdfs))
    log.info("  source : %s", raw_dir)
    log.info("  chroma : %s:%s", settings.chroma_host, settings.chroma_port)
    if settings.force_reingest:
        log.info("  (FORCE_REINGEST=true — full wipe requested)")
    log.info("=" * 60)

    try:
        reset_collection()
        log.info("ChromaDB collection cleared.")
    except Exception as exc:
        log.warning("ChromaDB reset failed (collection may not exist yet): %s", exc)

    for pdf in pdfs:
        try:
            result = await asyncio.to_thread(ingest_document, pdf)
            log.info("  [OK] %s — %d chunks", pdf.name, result.chunks_indexed)
        except Exception as exc:
            log.error("  [FAIL] %s: %s", pdf.name, exc)

    log.info("=" * 60)
    log.info("STARTUP INGESTION COMPLETE")
    log.info("=" * 60)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    asyncio.create_task(_startup_ingest())
    yield


app = FastAPI(title="Ingestion Service", version="0.1.0", lifespan=_lifespan)
setup_otel(app=app, service_suffix="ingestion")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ingest.router)
app.include_router(sources.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "ingestion-service"}


log.info("Ingestion service ready")
