"""Text splitting helpers (Phase 6, post page-logic removal).

Two flavours:
  - `chunk_documents(docs)` - legacy: chunk a list of pre-built
    Documents with the recursive char splitter. Kept for back-compat.
  - `chunk_markdown_doc(doc_meta, full_markdown)` - the active path:
    header-aware two-step splitter that doesn't break sentences.

The active splitter:
  1. `MarkdownHeaderTextSplitter` chops the full document at heading
     boundaries (#, ##, ###, ####) and tags each section with the
     enclosing headers (`h1`, `h2`, `h3`, `h4`).
  2. `RecursiveCharacterTextSplitter` char-splits each section. We use
     `keep_separator="end"` so the period (or `!`, `?`, `;`, `:`, `,`)
     stays at the END of the previous chunk instead of orphaning to
     the START of the next. Separators include `! ` / `? ` so questions
     and exclamations are preserved alongside `. `.
  3. Per chunk we
       - drop header-only / tiny fragments,
       - derive `section` (deepest header) and `section_title` (cleaned
         of markdown formatting + leading numbering),
       - prepend the heading chain to chunks that don't already begin
         with a heading - so retrievers and the LLM see section context
         inline, not just in metadata.

Page tracking was intentionally removed: pages are now joined "smartly"
upstream in `app.ingestion.pipeline._smart_join_pages` (cross-page
sentences are reunited), so chunks no longer break at page boundaries.
The trade-off is that citations no longer carry an exact page number.
"""
import re

from langchain_core.documents import Document
from langchain_text_splitters import (
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)

from app.config import settings
from app.observability.logging import get_logger
from app.observability.tracing import get_tracer

log = get_logger(__name__)
tracer = get_tracer(__name__)

# Markdown header levels we treat as section anchors.
_HEADERS_TO_SPLIT_ON = [
    ("#", "h1"),
    ("##", "h2"),
    ("###", "h3"),
    ("####", "h4"),
]

# Minimum body length for a chunk to be kept.
_MIN_CHUNK_CHARS = 80

# For deriving `section_title` from raw header text.
_LEADING_NUMBERING_RE = re.compile(r"^\s*\d+(?:\.\d+)*\.?\s*")
_MD_INLINE_FORMATTING_RE = re.compile(r"[*_`]+")


def _clean_section_title(header: str) -> str:
    """Extract a clean section title from a Markdown heading.

    Examples:
      "**1. Refund Policy**"             -> "Refund Policy"
      "2. Theft & Incident Handling"     -> "Theft & Incident Handling"
      "5.3. Premium Calculations"        -> "Premium Calculations"
      "Introduction"                     -> "Introduction"
      "1"                                -> "1"  (numbering-only falls back)
    """
    if not header:
        return ""
    no_formatting = _MD_INLINE_FORMATTING_RE.sub("", header).strip()
    no_numbering = _LEADING_NUMBERING_RE.sub("", no_formatting).strip()
    return no_numbering or no_formatting


def _make_splitter() -> RecursiveCharacterTextSplitter:
    return RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        # Tried in order: paragraph -> line -> sentence terminators
        # -> clause -> word -> char. With `keep_separator="end"` the
        # terminator stays attached to the previous chunk, so chunks
        # end at clean punctuation instead of leaving orphan periods
        # at the start of the next chunk.
        separators=[
            "\n\n",
            "\n",
            ". ",
            "! ",
            "? ",
            "; ",
            ": ",
            ", ",
            " ",
            "",
        ],
        keep_separator="end",
    )


def chunk_documents(documents: list[Document]) -> list[Document]:
    """Legacy: chunk a list of pre-built Documents."""
    log.info(
        "Chunking %d docs (size=%d, overlap=%d) ...",
        len(documents),
        settings.chunk_size,
        settings.chunk_overlap,
    )
    chunks = _make_splitter().split_documents(documents)
    log.info("  -> %d chunks", len(chunks))
    return chunks


def _is_header_only(text: str) -> bool:
    """True when every non-blank line is a markdown header (`#`, `##`, …)."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return bool(lines) and all(ln.startswith("#") for ln in lines)


def _build_header_prefix(header_levels: dict[int, str]) -> str:
    """Render an outline of the current section's headers as markdown."""
    if not header_levels:
        return ""
    return "\n".join(
        f"{'#' * level} {header_levels[level]}"
        for level in sorted(header_levels.keys())
    )


def chunk_markdown_doc(
    doc_meta: dict,
    full_markdown: str,
) -> list[Document]:
    """Header-aware splitter with section metadata."""
    # Lazy import - avoids a cycle (ingestion -> rag -> ingestion).
    from app.ingestion.metadata import chunk_metadata

    with tracer.start_as_current_span("chunker.split_markdown") as span:
        span.set_attribute("chunker.source", doc_meta.get("source", ""))
        span.set_attribute("chunker.chunk_size", settings.chunk_size)
        span.set_attribute("chunker.chunk_overlap", settings.chunk_overlap)
        span.set_attribute("chunker.input_chars", len(full_markdown))

        log.info(
            "Chunking full markdown (size=%d, overlap=%d, %d chars) ...",
            settings.chunk_size,
            settings.chunk_overlap,
            len(full_markdown),
        )

        md_splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=_HEADERS_TO_SPLIT_ON,
            strip_headers=False,
        )
        sections = md_splitter.split_text(full_markdown)
        char_chunks = _make_splitter().split_documents(sections)
        log.info(
            "  -> %d sections -> %d char chunks (pre-filter)",
            len(sections),
            len(char_chunks),
        )

        out: list[Document] = []
        skipped_header_only = 0
        skipped_too_small = 0

        for chunk in char_chunks:
            cleaned = chunk.page_content.strip()
            cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)

            if not cleaned:
                continue
            if _is_header_only(cleaned):
                skipped_header_only += 1
                continue
            if len(cleaned) < _MIN_CHUNK_CHARS:
                skipped_too_small += 1
                continue

            # Header levels from MarkdownHeaderTextSplitter metadata.
            header_levels: dict[int, str] = {}
            for level, key in enumerate(("h1", "h2", "h3", "h4"), start=1):
                val = chunk.metadata.get(key)
                if val:
                    header_levels[level] = str(val).strip()

            section = (
                header_levels[max(header_levels)]
                if header_levels
                else ""
            )

            meta = chunk_metadata(doc_meta)
            for level, val in header_levels.items():
                meta[f"h{level}"] = val
            if section:
                meta["section"] = section
                title = _clean_section_title(section)
                if title:
                    meta["section_title"] = title

            # Prepend section context unless the chunk already begins with
            # a heading (e.g. the first chunk of a section, which keeps
            # its original heading thanks to strip_headers=False).
            if header_levels and not cleaned.lstrip().startswith("#"):
                prefix = _build_header_prefix(header_levels)
                cleaned = f"{prefix}\n\n{cleaned}"

            out.append(Document(page_content=cleaned, metadata=meta))

        # Per-document 1-based chunk index. Stamped AFTER the
        # header-only / too-small filter so what you see in the UI
        # citation ("chunk 12") matches what inspect_chroma --report
        # prints when you cross-reference the same source PDF.
        for idx, doc in enumerate(out, start=1):
            doc.metadata["chunk_index"] = idx

        span.set_attribute("chunker.sections", len(sections))
        span.set_attribute("chunker.chunks_raw", len(char_chunks))
        span.set_attribute("chunker.chunks_kept", len(out))
        span.set_attribute(
            "chunker.skipped_header_only", skipped_header_only
        )
        span.set_attribute("chunker.skipped_too_small", skipped_too_small)
        log.info(
            "  -> %d kept chunks (filtered: %d header-only, %d too-small)",
            len(out),
            skipped_header_only,
            skipped_too_small,
        )
        return out
