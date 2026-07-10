"""GET /sources/{filename} - download an indexed source PDF.

Allow-listed to data/knowledge_base/raw/ to prevent path traversal.
"""
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from agentic_backend.config import settings
from agentic_backend.observability.logging import get_logger

log = get_logger(__name__)
router = APIRouter()


def _safe_lookup(filename: str):
    safe_name = Path(filename).name
    candidate = (settings.raw_pdf_dir / safe_name).resolve()
    base = settings.raw_pdf_dir.resolve()
    if not candidate.is_relative_to(base) or not candidate.is_file():
        return None
    return candidate


@router.get("/sources/{filename}")
def get_source(filename: str) -> FileResponse:
    path = _safe_lookup(filename)
    if path is None:
        log.warning("Source not found or invalid: %r", filename)
        raise HTTPException(status_code=404, detail=f"not found: {filename}")
    log.info("Serving source: %s", path)
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=filename,
    )
