"""- per-document ingestion pipeline.

Single entry point: `ingest_document(pdf_path, extra_metadata=None)`
which is used by both the batch script and (future) the UI upload route.
"""
from agentic_backend.ingestion.pipeline import IngestionResult, ingest_document

__all__ = ["IngestionResult", "ingest_document"]
