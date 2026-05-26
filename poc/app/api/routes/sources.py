"""GET /sources/{filename} - download an indexed source PDF.

Allow-listed to data/raw/ and tests/fixtures/ to prevent path traversal.
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.config import POC_ROOT, settings
from app.observability.logging import get_logger

log = get_logger(__name__)
router = APIRouter()

_FIXTURES_DIR = POC_ROOT / "tests" / "fixtures"


def _safe_lookup(filename: str):
    if "/" in filename or "\\" in filename or ".." in filename:
        return None
    for base in (settings.raw_pdf_dir, _FIXTURES_DIR):
        candidate = base / filename
        if candidate.is_file():
            return candidate
    return None


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
