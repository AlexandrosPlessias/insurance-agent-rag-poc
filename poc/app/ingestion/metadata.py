"""Per-document metadata builder + JSON Schema validator.

Two flavours of metadata:
  - Document-level sidecar (poc/data/knowledge_base/metadata/<stem>.json)
    Validated against poc/data/knowledge_base/metadata/schema.json.
  - Chunk-level metadata attached to each ChromaDB record. Derived from
    the sidecar by flattening lists (Chroma metadata is scalar-only) and
    adding the page number.
"""
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from app.config import settings
from app.observability.logging import get_logger

log = get_logger(__name__)

_SCHEMA_CACHE: dict | None = None


def _load_schema() -> dict | None:
    global _SCHEMA_CACHE
    if _SCHEMA_CACHE is None:
        if settings.metadata_schema_path.exists():
            _SCHEMA_CACHE = json.loads(
                settings.metadata_schema_path.read_text(encoding="utf-8")
            )
        else:
            log.warning(
                "Metadata schema missing at %s; validation will be skipped",
                settings.metadata_schema_path,
            )
            _SCHEMA_CACHE = {}
    return _SCHEMA_CACHE or None


def _relative_source_path(pdf_path: Path) -> str:
    """Store source paths relative to the project root.

    Absolute paths leak the ingester's machine (`/mnt/c/Users/<name>/...`,
    employer-specific OneDrive folders, etc.) into tracked chunk reports
    and chunk metadata. Resolve relative-to-project-root when possible;
    fall back to the filename for files outside the tree.
    """
    project_root = Path(__file__).resolve().parents[3]
    try:
        return Path(pdf_path).resolve().relative_to(project_root).as_posix()
    except ValueError:
        return pdf_path.name


def _derive_year(filename: str) -> int | None:
    """Pull a 4-digit year out of the filename (e.g. ..._2020.pdf -> 2020)."""
    m = re.search(r"(?:19|20)\d{2}", filename)
    return int(m.group(0)) if m else None


def _derive_title(filename: str) -> str:
    """Filename to title: `Foo_Bar_2020.pdf` -> `Foo Bar 2020`."""
    stem = Path(filename).stem
    return re.sub(r"[_\-]+", " ", stem).strip()


def _first_paragraph(pages: list[dict], limit: int = 240) -> str:
    """Best-effort description: first non-heading paragraph of page 1."""
    if not pages:
        return ""
    text = pages[0].get("markdown", "") or ""
    for block in text.split("\n\n"):
        block = block.strip()
        if block and not block.startswith("#"):
            return block[:limit]
    return text[:limit]


def build_document_metadata(
    pdf_path: Path,
    pages: list[dict],
    extra: dict | None = None,
) -> dict:
    """Build the per-document sidecar JSON.

    Description and keywords come from an LLM summariser pass over the
    full document markdown (one call per PDF, returns both fields).
    `extra` overrides any field, so the upcoming UI upload form can
    short-circuit the summariser with manually-typed values.
    """
    extra = extra or {}

    description = extra.get("description") or ""
    keywords = list(extra.get("keywords") or [])

    if not description or not keywords:
        # Lazy import to keep config-time imports light.
        from app.ingestion.summarizer import summarize_document

        full_md = "\n\n".join(p.get("markdown", "") for p in pages)
        summary = summarize_document(full_md)
        if not description:
            description = summary.get("description", "") or _first_paragraph(
                pages
            )
        if not keywords:
            keywords = summary.get("keywords", []) or []

    meta: dict = {
        "doc_id": extra.get("doc_id") or pdf_path.stem,
        "source": pdf_path.name,
        "source_path": _relative_source_path(pdf_path),
        "title": extra.get("title") or _derive_title(pdf_path.name),
        "description": description,
        "year": (
            extra.get("year")
            or _derive_year(pdf_path.name)
            or datetime.now().year
        ),
        "keywords": keywords,
        "ingestion_date_time": datetime.now(timezone.utc).isoformat(),
        "page_count": len(pages),
    }
    # Optional schema fields
    for k in (
        "user_group",
        "language",
        "document_category",
        "channel",
        "activation_date_time",
        "source_url",
    ):
        if k in extra and extra[k] not in (None, ""):
            meta[k] = extra[k]

    validate_metadata(meta)
    return meta


def validate_metadata(meta: dict) -> None:
    """Best-effort validation. Logs warnings - never raises."""
    schema = _load_schema()
    if not schema:
        return
    try:
        import jsonschema
    except ImportError:
        log.debug("jsonschema not installed - skipping validation")
        return
    try:
        jsonschema.validate(meta, schema)
    except jsonschema.ValidationError as exc:
        path = ".".join(str(p) for p in exc.path) or "<root>"
        log.warning("Metadata validation: %s (at %s)", exc.message, path)


def write_metadata(path: Path, meta: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(meta, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    log.info("  -> wrote metadata to %s", path.name)


def chunk_metadata(doc_meta: dict) -> dict:
    """Flatten document metadata for ChromaDB (scalars only).

    Page-level tracking was removed in favour of clean cross-page
    text flow; chunk metadata is now derived purely from the document
    sidecar plus header info added by the chunker.
    """
    out: dict = {}
    for k, v in doc_meta.items():
        if isinstance(v, (str, int, float, bool)):
            out[k] = v
        elif isinstance(v, list):
            # Chroma metadata values must be scalars; join list to string.
            out[k] = ", ".join(str(x) for x in v) if v else ""
    return out
