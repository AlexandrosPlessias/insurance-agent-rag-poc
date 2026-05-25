"""PyMuPDF-based PDF loader producing per-page document records."""
from pathlib import Path

import fitz  # PyMuPDF
from langchain_core.documents import Document


def load_pdf(pdf_path: Path) -> list[Document]:
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
    return docs


def load_pdfs(directory: Path) -> list[Document]:
    documents: list[Document] = []
    for pdf_path in sorted(directory.glob("*.pdf")):
        documents.extend(load_pdf(pdf_path))
    return documents
