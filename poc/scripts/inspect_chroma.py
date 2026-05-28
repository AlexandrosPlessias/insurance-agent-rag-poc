"""Inspect the local ChromaDB collection - for debugging the ingestion.

Run from poc/ (after activating the venv):

  python scripts/inspect_chroma.py                       # summary
  python scripts/inspect_chroma.py --sample 5            # 5 sample chunks
  python scripts/inspect_chroma.py --source NAME.pdf     # filter by source
  python scripts/inspect_chroma.py --search "deductible" # similarity search
  python scripts/inspect_chroma.py --metadata            # full metadata dump
  python scripts/inspect_chroma.py --all                 # dump every chunk

  # Generate one inspection report per source PDF (stats + all chunks):
  python scripts/inspect_chroma.py --report
  python scripts/inspect_chroma.py --report --source NAME.pdf
"""
import argparse
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402
from app.observability.logging import (  # noqa: E402
    configure_logging,
    get_logger,
)
from app.rag.retriever import retrieve  # noqa: E402
from app.rag.vectorstore import get_vectorstore  # noqa: E402

configure_logging("WARNING")
log = get_logger("inspect_chroma")


# ---------- pretty-printers for the "live" mode ----------


def _format_chunk(doc: str, meta: dict, idx: int, show_meta: bool) -> None:
    src = meta.get("source", "?")
    section = (
        meta.get("section_title") or meta.get("section") or ""
    ).strip()
    bits = [f"[{idx}] {src}"]
    if section:
        bits.append(section)
    print("\n" + "  ·  ".join(bits))
    if show_meta:
        for k in sorted(meta.keys()):
            v = meta[k]
            if isinstance(v, str) and len(v) > 80:
                v = v[:77] + "..."
            print(f"    {k}: {v}")
    body = doc.strip()
    if len(body) > 500:
        body = body[:500] + " ..."
    print("  ---")
    for line in body.splitlines():
        print(f"  {line}")


# ---------- report-file generators ----------


_DOC_LEVEL_KEYS = (
    "doc_id",
    "title",
    "year",
    "description",
    "keywords",
    "language",
    "document_category",
    "page_count",
    "ingestion_date_time",
    "source_path",
)


def _md_escape(value) -> str:
    text = str(value)
    if len(text) > 240:
        text = text[:240] + "..."
    return text.replace("|", r"\|").replace("\n", " ")


def _render_report(source: str, docs: list[str], metas: list[dict]) -> str:
    """Build the Markdown body for one source PDF's chunk report."""
    if not docs:
        return f"# {source}\n\nNo chunks indexed for this document.\n"

    char_lens = [len(d) for d in docs]
    total_chars = sum(char_lens)
    n = len(docs)

    # Document-level metadata - take the first chunk's view (all chunks
    # of the same PDF share the same document-level fields).
    doc_meta = metas[0] if metas else {}

    section_counter = Counter(
        (m.get("section_title") or m.get("section") or "(no section)")
        for m in metas
    )

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    lines: list[str] = []
    lines.append(f"# Chunk Inspection Report - {source}")
    lines.append("")
    lines.append(f"*Generated: {now}*")
    lines.append("")

    # --- Document metadata table ---
    lines.append("## Document metadata")
    lines.append("")
    lines.append("| Field | Value |")
    lines.append("|---|---|")
    for k in _DOC_LEVEL_KEYS:
        if k in doc_meta and doc_meta[k] not in (None, "", []):
            lines.append(f"| `{k}` | {_md_escape(doc_meta[k])} |")
    lines.append("")

    # --- Stats ---
    lines.append("## Statistics")
    lines.append("")
    lines.append(f"- **Total chunks**: {n}")
    lines.append(f"- **Total characters**: {total_chars:,}")
    lines.append(f"- **Avg chars / chunk**: {total_chars / n:.1f}")
    lines.append(
        "- **Min / median / max chars**: "
        f"{min(char_lens)} / {int(statistics.median(char_lens))} / "
        f"{max(char_lens)}"
    )
    lines.append(f"- **Configured chunk_size**: {settings.chunk_size}")
    lines.append(
        f"- **Configured chunk_overlap**: {settings.chunk_overlap}"
    )
    lines.append("")

    # --- Section distribution ---
    lines.append("### Section distribution (by `section_title`)")
    lines.append("")
    lines.append("| Section | Chunks |")
    lines.append("|---|---|")
    for sec, cnt in sorted(section_counter.items()):
        lines.append(f"| {_md_escape(sec)} | {cnt} |")
    lines.append("")

    # --- All chunks ---
    lines.append("## Chunks")
    lines.append("")
    for i, (doc, meta) in enumerate(zip(docs, metas), start=1):
        section = (
            meta.get("section_title") or meta.get("section") or ""
        )
        title_bits = [f"Chunk {i}"]
        if section:
            title_bits.append(section)
        lines.append("### " + "  ·  ".join(title_bits))
        lines.append("")
        lines.append(f"*{len(doc)} chars*")
        lines.append("")
        lines.append("**Metadata:**")
        lines.append("")
        for k in sorted(meta.keys()):
            lines.append(f"- `{k}`: {_md_escape(meta[k])}")
        lines.append("")
        lines.append("**Content:**")
        lines.append("")
        lines.append("```markdown")
        lines.append(doc)
        lines.append("```")
        lines.append("")
    return "\n".join(lines)


def _generate_reports(
    collection,
    output_dir: Path,
    source_filter: str | None,
) -> list[Path]:
    """Write one Markdown report per source PDF into output_dir."""
    where = {"source": source_filter} if source_filter else None
    get_kwargs = {"include": ["documents", "metadatas"]}
    if where is not None:
        get_kwargs["where"] = where
    data = collection.get(**get_kwargs)
    docs = data.get("documents") or []
    metas = data.get("metadatas") or []

    # Group by source
    by_source: dict[str, dict[str, list]] = defaultdict(
        lambda: {"documents": [], "metadatas": []}
    )
    for doc, meta in zip(docs, metas):
        src = (meta or {}).get("source", "unknown")
        by_source[src]["documents"].append(doc)
        by_source[src]["metadatas"].append(meta or {})

    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for src in sorted(by_source.keys()):
        stem = Path(src).stem or "unknown"
        out_path = output_dir / f"{stem}_chunks.md"
        report = _render_report(
            src,
            by_source[src]["documents"],
            by_source[src]["metadatas"],
        )
        out_path.write_text(report, encoding="utf-8")
        n = len(by_source[src]["documents"])
        print(f"  -> {out_path.name}  ({n} chunks)")
        written.append(out_path)
    return written


# ---------- main ----------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inspect ChromaDB content (chunks, metadata, search).",
    )
    parser.add_argument(
        "--source",
        help="Filter by source filename",
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=3,
        help="Show N sample chunks (default 3, ignored with --all)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Dump every chunk (overrides --sample) - can be very long",
    )
    parser.add_argument(
        "--search",
        help="Run a similarity_search query instead of sampling",
    )
    parser.add_argument(
        "--k",
        type=int,
        default=5,
        help="K results for --search (default 5)",
    )
    parser.add_argument(
        "--metadata",
        action="store_true",
        help="Dump every metadata field on each sample",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help=(
            "Generate one Markdown chunk report per source PDF "
            "(stats + every chunk + metadata)"
        ),
    )
    parser.add_argument(
        "--report-dir",
        help=(
            "Output directory for --report (default: "
            "data/knowledge_base/reports/)"
        ),
    )
    args = parser.parse_args()

    vs = get_vectorstore()
    collection = vs._collection
    total = collection.count()

    print("\n=== ChromaDB inspector ===")
    print(f"  collection : {settings.chroma_collection}")
    print(f"  path       : {settings.chroma_persist_dir}")
    print(f"  total docs : {total}")

    if total == 0:
        print(
            "\nNo chunks indexed yet. Run: python scripts/ingest_pdfs.py"
        )
        return 0

    # ---- per-PDF report mode ----
    if args.report:
        report_dir = (
            Path(args.report_dir).resolve()
            if args.report_dir
            else settings.processed_dir.parent / "reports"
        )
        print(f"\n=== Writing per-PDF reports to {report_dir} ===")
        written = _generate_reports(
            collection, report_dir, args.source
        )
        if not written:
            print("  (no chunks matched the filter)")
            return 0
        print(f"\nDone. {len(written)} report(s) written.")
        return 0

    # Per-source counts
    all_data = collection.get(include=["metadatas"])
    metas = all_data.get("metadatas") or []
    sources = Counter(m.get("source", "?") for m in metas)
    print(f"\nSources ({len(sources)}):")
    for src, cnt in sorted(sources.items()):
        print(f"  {cnt:>5} chunks  |  {src}")

    # Section distribution if a single source is filtered
    if args.source and args.source in sources:
        sections = Counter(
            (m.get("section_title") or m.get("section") or "(no section)")
            for m in metas
            if m.get("source") == args.source
        )
        print(f"\nSections in {args.source}:")
        for sec, cnt in sorted(sections.items()):
            print(f"  {cnt:>3} chunks  |  {sec}")

    if args.search:
        print(f"\n=== similarity_search: {args.search!r} (k={args.k}) ===")
        try:
            results = retrieve(args.search, k=args.k)
        except Exception as exc:  # noqa: BLE001
            print(f"  ERROR: {exc}")
            return 1
        if not results:
            print("  (no results)")
        for i, r in enumerate(results, start=1):
            preview = r.content.strip()
            if len(preview) > 300:
                preview = preview[:300] + " ..."
            print(f"\n[{i}] {r.as_citation()}")
            print(f"  {preview}")
        return 0

    # Sample chunks (optional source filter, optional --all)
    where = {"source": args.source} if args.source else None
    limit = None if args.all else args.sample
    header = (
        "All chunks" if args.all
        else f"Sample chunks (limit={args.sample})"
    )
    if args.source:
        header += f" for {args.source}"
    print(f"\n=== {header} ===")
    get_kwargs = {
        "include": ["documents", "metadatas"],
    }
    if where is not None:
        get_kwargs["where"] = where
    if limit is not None:
        get_kwargs["limit"] = limit
    sample = collection.get(**get_kwargs)
    docs = sample.get("documents") or []
    sample_metas = sample.get("metadatas") or []
    if not docs:
        print("  (no chunks matched)")
        return 0
    for i, (doc, meta) in enumerate(zip(docs, sample_metas), start=1):
        _format_chunk(doc, meta or {}, i, args.metadata)
    return 0


if __name__ == "__main__":
    sys.exit(main())
