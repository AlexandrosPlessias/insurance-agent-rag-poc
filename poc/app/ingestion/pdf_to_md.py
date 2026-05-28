"""Per-page PDF -> Markdown via pymupdf4llm.

Preserves layout (headings, tables, lists) better than the raw PyMuPDF
text extraction used in earlier phases.
"""
from pathlib import Path

from app.observability.logging import get_logger

log = get_logger(__name__)


def pdf_to_markdown_pages(pdf_path: Path) -> list[dict]:
    """Return [{"page": int, "markdown": str}, ...] - one entry per page.

    Uses `pymupdf4llm.to_markdown(page_chunks=True)`. The library returns
    either a string (when page_chunks=False) or a list of dicts with a
    `metadata` block (page index) and `text` field. We normalise both.
    """
    import pymupdf4llm  # heavy import - kept lazy

    log.info("PDF -> Markdown: %s", pdf_path.name)
    raw = pymupdf4llm.to_markdown(
        str(pdf_path),
        page_chunks=True,
        write_images=False,
    )

    pages: list[dict] = []
    if isinstance(raw, str):
        pages.append({"page": 1, "markdown": raw})
    else:
        for idx, item in enumerate(raw):
            if isinstance(item, dict):
                meta = item.get("metadata", {}) or {}
                page = meta.get("page")
                if page is None:
                    page = idx + 1
                text = item.get("text") or item.get("markdown") or ""
            else:
                page = idx + 1
                text = str(item)
            pages.append({"page": int(page), "markdown": text})

    log.info("  -> %d pages of markdown", len(pages))
    return pages
