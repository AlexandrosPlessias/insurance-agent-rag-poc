"""Phase 9 ReportDocument writers.

Three serialisers, one per delivery mode. All consume the same
ReportDocument; the writers add format-specific rendering on top.

  markdown_writer  -> str       (for st.markdown + .md downloads)
  docx_writer      -> bytes     (python-docx)
  pdf_writer       -> bytes     (reportlab)
"""
from app.reporting.writers.docx_writer import render_docx
from app.reporting.writers.markdown_writer import render_markdown
from app.reporting.writers.pdf_writer import render_pdf

__all__ = ["render_markdown", "render_docx", "render_pdf"]
