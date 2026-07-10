"""POST /ingest - accepts a PDF upload + optional metadata, then indexes.

Wraps `agentic_backend.ingestion.pipeline.ingest_document` so the same
per-document flow used by `scripts/ingest_pdfs.py` is available to any UI
or automation.

Usage from curl:
  curl -F "file=@policy.pdf" -F "title=My Policy" \
       -F "keywords=auto,collision" http://localhost:8000/ingest
"""
import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from agentic_backend.config import settings
from agentic_backend.ingestion.pipeline import ingest_document
from agentic_backend.observability.logging import get_logger

log = get_logger(__name__)
router = APIRouter()


def _parse_keywords(value: Optional[str]) -> list[str]:
    """Accept either a JSON array or a comma-separated string."""
    if not value:
        return []
    value = value.strip()
    if value.startswith("["):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [str(x) for x in parsed]
        except json.JSONDecodeError:
            pass
    return [k.strip() for k in value.split(",") if k.strip()]


@router.post("/ingest")
async def ingest_pdf(
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    year: Optional[int] = Form(None),
    keywords: Optional[str] = Form(None),
    language: Optional[str] = Form(None),
    document_category: Optional[str] = Form(None),
) -> dict:
    if not file.filename:
        raise HTTPException(400, "Missing filename")
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are supported")

    # Strip any directory components from the upload filename before writing
    # to disk — prevents path traversal (e.g. "../../secrets.env").
    safe_name = Path(file.filename).name
    settings.raw_pdf_dir.mkdir(parents=True, exist_ok=True)
    target = (settings.raw_pdf_dir / safe_name).resolve()
    if not target.is_relative_to(settings.raw_pdf_dir.resolve()):
        raise HTTPException(400, "Invalid filename")
    target.write_bytes(await file.read())
    log.info("Stored upload at %s", target)

    extra: dict = {}
    if title:
        extra["title"] = title
    if description:
        extra["description"] = description
    if year is not None:
        extra["year"] = int(year)
    if language:
        extra["language"] = language
    if document_category:
        extra["document_category"] = _parse_keywords(document_category)
    if keywords:
        extra["keywords"] = _parse_keywords(keywords)

    try:
        result = ingest_document(target, extra_metadata=extra)
    except Exception as exc:  # noqa: BLE001
        log.exception("Ingestion failed for %s: %s", file.filename, exc)
        raise HTTPException(500, "Ingestion failed — see server logs") from exc

    return {
        "doc_id": result.doc_id,
        "source": target.name,
        "page_count": result.page_count,
        "chunks_indexed": result.chunks_indexed,
        "duration_s": round(result.duration_s, 3),
        "markdown_path": str(result.markdown_path),
        "metadata_path": str(result.metadata_path),
    }
