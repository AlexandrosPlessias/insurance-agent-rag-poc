"""Per-document ingestion pipeline (Phase 6).

PDF -> Markdown -> metadata sidecar -> chunks -> ChromaDB.

Single entry point: `ingest_document(pdf_path, extra_metadata=None)`.
Idempotent enough for re-runs (the same chunks are added again, which
duplicates them; call `reset_collection()` first for a clean slate).
"""
import time
from dataclasses import dataclass, field
from pathlib import Path

import re

from app.config import settings
from app.ingestion.metadata import build_document_metadata, write_metadata
from app.ingestion.pdf_to_md import pdf_to_markdown_pages
from app.observability.logging import get_logger
from app.observability.tracing import get_tracer
from app.rag.chunker import chunk_markdown_doc
from app.rag.vectorstore import add_documents, delete_by_source

log = get_logger(__name__)
tracer = get_tracer(__name__)


_BLOCK_START = re.compile(r"^(#{1,6}\s|[-*]\s|\d+\.\s|>|```)")


def _smart_join_pages(pages: list[dict]) -> str:
    """Concatenate pages into one body; reunite cross-page sentences.

    Heuristics (pymupdf4llm always emits clean per-page markdown):
      - Previous page ends with terminating punctuation OR next page starts
        with a markdown block (heading, list, blockquote, fence)
            -> paragraph break ("\\n\\n") between them.
      - Otherwise (previous ends mid-clause, next starts lowercase)
            -> join with a single space so the sentence is reunited.
    """
    parts: list[str] = []
    for p in pages:
        text = (p.get("markdown") or "").rstrip()
        if not text:
            continue
        if not parts:
            parts.append(text)
            continue
        prev = parts[-1]
        prev_ends_punct = prev[-1] in ".!?:;" if prev else False
        next_is_block = bool(_BLOCK_START.match(text.lstrip()))
        if next_is_block or prev_ends_punct:
            parts.append("\n\n")
        else:
            # Mid-clause page transition - reunite as one sentence.
            parts.append(" ")
        parts.append(text)
    return "".join(parts)


@dataclass
class IngestionResult:
    doc_id: str
    source_path: Path
    markdown_path: Path
    metadata_path: Path
    page_count: int
    chunks_indexed: int
    duration_s: float
    errors: list[str] = field(default_factory=list)


def ingest_document(
    pdf_path: Path | str,
    extra_metadata: dict | None = None,
) -> IngestionResult:
    """Run the full per-document ingestion pipeline.

    Parameters
    ----------
    pdf_path:
        Path to the source PDF. Typically inside `data/knowledge_base/raw/`
        but any readable path works.
    extra_metadata:
        Optional overrides for the sidecar JSON - e.g. title, keywords,
        language, document_category. The UI upload form will populate
        these.
    """
    pdf_path = Path(pdf_path).resolve()
    if not pdf_path.is_file():
        raise FileNotFoundError(pdf_path)

    with tracer.start_as_current_span("ingestion.pipeline") as span:
        span.set_attribute("ingestion.source", pdf_path.name)

        t0 = time.perf_counter()
        log.info("=== Ingesting %s ===", pdf_path.name)

        # 1. PDF -> per-page Markdown
        pages = pdf_to_markdown_pages(pdf_path)

        # 2. Write the full markdown to processed/ - one .md per PDF, no
        #    page markers. Pages are joined "smartly": a clean paragraph
        #    break between pages where the previous page ended cleanly
        #    (terminating punctuation), or a single space where the
        #    previous page ended mid-sentence (so the sentence is reunited
        #    instead of being severed at the page boundary). This trades
        #    page-level citations for clean text flow - chunks no longer
        #    cut sentences at page transitions.
        settings.processed_dir.mkdir(parents=True, exist_ok=True)
        md_path = settings.processed_dir / (pdf_path.stem + ".md")
        md_text = _smart_join_pages(pages)
        md_path.write_text(md_text, encoding="utf-8")
        span.set_attribute("ingestion.markdown_chars", len(md_text))
        log.info(
            "  -> wrote %d-char markdown to processed/%s",
            len(md_text),
            md_path.name,
        )

        # 3. Document-level metadata sidecar (validated against schema.json)
        doc_meta = build_document_metadata(pdf_path, pages, extra_metadata)
        meta_path = settings.metadata_dir / (pdf_path.stem + ".json")
        write_metadata(meta_path, doc_meta)

        # 4. Idempotent re-ingest: delete any existing chunks for this
        #    source filename so a second `ingest_document(same_pdf)` call
        #    replaces them instead of inserting duplicates.
        delete_by_source(pdf_path.name)

        # 5. Chunk the full Markdown body and index the new chunks.
        chunks = chunk_markdown_doc(doc_meta, md_text)
        n = add_documents(chunks)

        elapsed = time.perf_counter() - t0
        span.set_attribute("ingestion.page_count", len(pages))
        span.set_attribute("ingestion.chunks_indexed", n)
        span.set_attribute("ingestion.duration_s", round(elapsed, 3))
        log.info(
            "=== Done %s: %d pages, %d chunks indexed in %.2fs ===",
            pdf_path.name,
            len(pages),
            n,
            elapsed,
        )
        return IngestionResult(
            doc_id=doc_meta["doc_id"],
            source_path=pdf_path,
            markdown_path=md_path,
            metadata_path=meta_path,
            page_count=len(pages),
            chunks_indexed=n,
            duration_s=elapsed,
        )
