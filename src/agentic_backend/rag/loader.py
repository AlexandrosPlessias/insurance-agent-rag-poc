"""PyMuPDF-based PDF loader producing per-page document records."""
from pathlib import Path

import fitz  # PyMuPDF
from langchain_core.documents import Document

from agentic_backend.observability.logging import get_logger

log = get_logger(__name__)


def load_pdf(pdf_path: Path) -> list[Document]:
    log.info("Loading PDF: %s", pdf_path.name)
    docs: list[Document] = []
    with fitz.open(pdf_path) as pdf:
        for page_index, page in enumerate(pdf, start=1):
            text = page.get_text("text").strip()
            if not text:
                continue
            docs.append(
                Document(
                    page_content=text,
                    metadata={
                        "source": pdf_path.name,
                        "source_path": str(pdf_path),
                        "page": page_index,
                        "total_pages": pdf.page_count,
                    },
                )
            )
    log.info("  → %d pages with text from %s", len(docs), pdf_path.name)
    return docs


def load_pdfs(directory: Path) -> list[Document]:
    pdf_files = sorted(directory.glob("*.pdf"))
    log.info("Found %d PDF file(s) in %s", len(pdf_files), directory)
    documents: list[Document] = []
    for pdf_path in pdf_files:
        documents.extend(load_pdf(pdf_path))
    return documents
