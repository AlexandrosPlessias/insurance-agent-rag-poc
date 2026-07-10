# Ingestion & Chunking Pipeline

How PDFs in `src/data/knowledge_base/raw/` end up as queryable chunks in ChromaDB, and why each step looks the way it does.

For a one-page operational quickstart see [USAGE.md §3](../../USAGE.md). This document explains the **logic and design decisions** behind the code.

---

## 1. Pipeline at a glance

```
src/data/knowledge_base/raw/<doc>.pdf
              │
              ▼  PyMuPDF4LLM (page_chunks=True)
        list[{page, markdown}]
              │
              ▼  _smart_join_pages()
        one Markdown body (no page markers)
              │
              ├─► src/data/knowledge_base/processed/<doc>.md
              │
              ├─► LLM summariser (one round-trip per doc)
              │     {description, keywords}
              │
              ▼  build_document_metadata() + write_metadata()
        src/data/knowledge_base/metadata/<doc>.json
              │
              ▼  chunk_markdown_doc()
        Header-aware + recursive-character chunks
              │
              ▼  add_documents()
        ChromaDB collection `policies`
```

Single entry point: [`ingest_document(pdf_path, extra_metadata)`](../../src/agentic_backend/ingestion/pipeline.py). Used by the batch script, the smoke test, and the `POST /ingest` endpoint.

Per-doc cost: **one LLM call** for the summariser, **one batch embedding** call across all chunks. Documents are ingested in parallel by `scripts/ingest_pdfs.py` (default 4 workers, governed by `INGEST_WORKERS` and Ollama's `OLLAMA_NUM_PARALLEL`).

---

## 2. PDF → Markdown

We use [`pymupdf4llm`](https://pypi.org/project/pymupdf4llm/) (same publisher as PyMuPDF). It preserves layout (headings, tables, lists) and produces one Markdown blob per page when called with `page_chunks=True`.

Function: [`pdf_to_markdown_pages(pdf_path)`](../../src/agentic_backend/ingestion/pdf_to_md.py).

Returns `list[{"page": int, "markdown": str}]` — one entry per page, page number preserved at this stage even though we drop it downstream.

---

## 3. Smart page joining (no markers)

Naive `"\n\n".join(pages)` causes a real problem: pymupdf4llm extracts page text *page by page*, so any sentence that spans a page boundary gets cleaved. For example, the PDF's natural flow

> *Such actions expose the organization to legal liability and create unacceptable safety risks.*

extracts as

- Page 1 ending: `"Such actions expose"`
- Page 2 beginning: `"the organization to legal liability..."`

If we then insert `"\n\n"` between pages, the recursive splitter sees that as the strongest paragraph break and obediently cuts the chunk right there — severing the sentence.

`_smart_join_pages` ([app/ingestion/pipeline.py](../../src/agentic_backend/ingestion/pipeline.py)) handles this with a small heuristic:

| Previous page ends with | Next page starts with | Join character |
|---|---|---|
| `.`, `!`, `?`, `:`, `;` | (anything) | `\n\n` (paragraph break) |
| any non-terminator | markdown block (`#`, `- `, `1. `, `>`, ` ``` `) | `\n\n` (paragraph break) |
| any non-terminator | regular text (lowercase, mid-clause) | `" "` (single space — reunite the sentence) |

Result: clean text flow, no marker comments, no orphan periods, no severed sentences at page boundaries.

**Trade-off**: chunks no longer carry an exact page number. Citations now read `source.pdf · Refund Policy` instead of `source.pdf · p.3`. Section names + section titles ([§7 below](#7-section-metadata)) remain the primary locator.

---

## 4. Document metadata sidecar

Function: [`build_document_metadata(pdf_path, pages, extra)`](../../src/agentic_backend/ingestion/metadata.py).

Per document we write a JSON sidecar at `src/data/knowledge_base/metadata/<stem>.json`, validated (best-effort) against [`metadata/schema.json`](../src/data/knowledge_base/metadata/schema.json).

Field sources:

| Field | How it's set |
|---|---|
| `doc_id` | PDF filename stem (override via `extra`) |
| `source`, `source_path` | from `pdf_path` |
| `title` | filename `→` "_" / "-" replaced (override via `extra`) |
| `year` | regex `(19\|20)\d{2}` against filename → `extra` → current year fallback |
| `description` | **LLM summariser** (override via `extra`) |
| `keywords` | **LLM summariser** (override via `extra`) |
| `ingestion_date_time` | `now()` in UTC ISO-8601 |
| `page_count` | number of pages from PyMuPDF |
| `language`, `document_category`, `user_group`, `channel`, `activation_date_time`, `source_url` | only present when supplied via `extra` (UI form, API call) |

---

## 5. LLM summariser

Function: [`summarize_document(markdown)`](../../src/agentic_backend/ingestion/summarizer.py). Externalised prompt at [`prompts/document_summary.txt`](../../src/agentic_backend/llm/prompts/document_summary.txt).

- **One LLM round-trip** per document, returning JSON `{description, keywords}`.
- Description: ≤250 chars, neutral tone, what the document is about.
- Keywords: 5–10 lowercase hyphen-joined strings. Designed as semantic-search anchors (`refund-policy`, `claims-procedure`, `theft-handling`, `2024-guidelines`, …).
- Input is truncated to ~8 000 chars (top half + bottom half) so very long docs don't blow the context window.
- Failure-tolerant: if the call errors or the JSON is unparseable, we log a warning and fall back to filename-derived title and the first paragraph for description.
- Traced as `ingestion.summarize` (visible in Aspire).

The `extra_metadata` argument to `ingest_document` short-circuits the summariser when the UI form (future) supplies `description` and `keywords` manually.

---

## 6. Chunking: header-aware two-step

Function: [`chunk_markdown_doc(doc_meta, full_markdown)`](../../src/agentic_backend/rag/chunker.py).

### Step 1 — `MarkdownHeaderTextSplitter`

Splits at `#`, `##`, `###`, `####`. `strip_headers=False` keeps the heading line as the first line of its section's text, so the *first* char-chunk of each section naturally contains its header. Subsequent char-chunks (within the same section) get the heading **prepended in code** (see step 3) so every chunk has its section context inline.

Each section's `chunk.metadata` carries `h1`, `h2`, `h3`, `h4` for whichever heading levels were in force at that point in the document.

### Step 2 — `RecursiveCharacterTextSplitter`

Within each header-section, char-split with:

```python
chunk_size      = settings.chunk_size       # default 1200
chunk_overlap   = settings.chunk_overlap    # default 200
keep_separator  = "end"                     # <-- crucial
separators      = ["\n\n", "\n",
                   ". ", "! ", "? ",       # sentence terminators
                   "; ", ": ", ", ",       # clause terminators
                   " ", ""]
```

**Why `keep_separator="end"`** (and not the LangChain default `True`/`"start"`): when the splitter chops at `". "`, the default behaviour leaves the period attached to the **next** chunk — so chunk N ends mid-sentence at `"intact"` (no period) and chunk N+1 starts with `". Items must be returned..."`. Setting `keep_separator="end"` keeps the period with the previous chunk, so chunk N ends cleanly at `"...intact."` and chunk N+1 starts at the next word.

**Why all those separators**: each falls back to the next when the current one can't satisfy `chunk_size`. Sentence terminators (`. `, `! `, `? `) come before clause terminators (`; `, `: `, `, `) so the splitter prefers ending at sentence boundaries.

### Step 3 — per-chunk post-processing

For each char-chunk we:

1. **Strip & collapse whitespace** — collapse any `\n{3,}` back to `\n\n` (cleans up stacked breaks where heading whitespace overlaps).
2. **Skip header-only fragments** — if every line starts with `#`, drop it. (These happen when consecutive headings appear without body content between.)
3. **Skip too-small fragments** — `len(cleaned) < 80` chars are dropped.
4. **Compute `section` and `section_title`** — see [§7 below](#7-section-metadata).
5. **Prepend the heading chain** — if the chunk doesn't already start with a heading (i.e. it's the 2nd or 3rd char-chunk of a long section), prepend the section's `h1..h4` outline so both the embedding and the answering LLM see the section context inline.

---

## 7. Section metadata

For each chunk:

| Field | Value | Example |
|---|---|---|
| `h1`, `h2`, `h3`, `h4` | enclosing heading text, verbatim | `h2 = "**1. Refund Policy**"` |
| `section` | deepest non-empty heading, verbatim | `"**1. Refund Policy**"` |
| `section_title` | `section` with markdown formatting + leading numbering stripped | `"Refund Policy"` |

`section_title` is the **primary topic anchor for semantic search filters**: it's stable across documents regardless of numbering and formatting. Example:

```python
collection.query(
    query_texts=["what's the refund window?"],
    where={"section_title": "Refund Policy"},
    n_results=5,
)
# Returns the "Refund Policy" chunk from every PDF in the index.
```

`section_title` derivation is in `_clean_section_title()` ([chunker.py](../../src/agentic_backend/rag/chunker.py)):

```
"**1. Refund Policy**"            -> "Refund Policy"
"2. Theft & Incident Handling"    -> "Theft & Incident Handling"
"5.3. Premium Calculations"       -> "Premium Calculations"
"Introduction"                    -> "Introduction"
"1"                               -> "1"  (numbering-only falls back)
```

---

## 8. Chunk-size tuning

Defaults are `chunk_size=1200`, `chunk_overlap=200` (≈17%). The README has the rationale table. Quick guide:

| Symptom | Action |
|---|---|
| Answers miss details you know are in the doc | chunks too small — try 1500 / 250 |
| Answers wander, include unrelated facts | chunks too large — try 900 / 150 |
| Citations point at chunks that look fragmented or empty | the `_MIN_CHUNK_CHARS` filter (80) is too aggressive — adjust in [chunker.py](../../src/agentic_backend/rag/chunker.py) |
| You see periods at start of chunks | `keep_separator="end"` isn't applied — check your branch is up to date |

After any tuning change:

```bash
cd poc && source .venv/bin/activate
python scripts/reset_stores.py
python scripts/ingest_pdfs.py
python scripts/inspect_chroma.py --report   # full audit
```

---

## 9. Storage in ChromaDB

`add_documents(chunks)` ([app/rag/vectorstore.py](../../src/agentic_backend/rag/vectorstore.py)) embeds via `nomic-embed-text` and writes to the persistent Chroma collection at `src/data/chroma_db/`. Chroma stores per-record:

- `documents` → the chunk text (with prepended heading where applicable)
- `embeddings` → the vector
- `metadatas` → all the **scalar** fields from `chunk_metadata()` (lists in the sidecar get flattened to comma-separated strings)

Filterable metadata fields per chunk (post-Phase-6, post-page-removal):

`doc_id`, `source`, `source_path`, `title`, `year`, `description`, `keywords`, `language`, `document_category`, `channel`, `ingestion_date_time`, `activation_date_time`, `source_url`, `page_count`, `h1`, `h2`, `h3`, `h4`, `section`, `section_title`.

---

## 10. Re-ingestion semantics

`ingest_document` is **not idempotent by default**: calling it twice on the same PDF inserts a fresh set of chunks alongside the existing ones (Chroma's `add` doesn't dedupe). For a clean rebuild:

```bash
python scripts/reset_stores.py        # wipe collection + memory
python scripts/ingest_pdfs.py         # re-index from raw/
```

If you want per-document idempotency without nuking everything, you'd add a delete-by-source step before `add_documents` in the pipeline. Not currently implemented; it's a small change if needed.

---

## 11. UI upload pipeline

The `POST /ingest` endpoint ([api/routes/ingest.py](../../src/agentic_backend/api/routes/ingest.py)) wraps the same `ingest_document` function:

```bash
curl -F "file=@my-policy.pdf" \
     -F "title=My Auto Policy 2024" \
     -F "year=2024" \
     -F "keywords=auto,collision,deductible" \
     -F "language=en" \
     -F "document_category=policy,personal-lines" \
     http://localhost:8000/ingest
```

Form fields populate `extra_metadata` — supplying `description` or `keywords` here short-circuits the LLM summariser, which is useful when the uploader already knows the metadata. The React SPA upload form hits this exact endpoint.

---

## 12. Observability

Each pipeline run emits OpenTelemetry spans visible in Aspire:

- `ingestion.summarize` — LLM call with `input_chars`, `description.chars`, `keywords.count`.
- `rag.retrieve` — span on every similarity search at query time, attributes `retrieve.k`, `retrieve.result_count`, `retrieve.duration_s`.

Stderr logs use the standard format and are tagged by module (`app.ingestion.pipeline`, `app.rag.chunker`, etc.) — also forwarded to Aspire as structured logs with trace correlation.

---

## 13. References

| Concern | File |
|---|---|
| Pipeline orchestration | [src/agentic_backend/ingestion/pipeline.py](../../src/agentic_backend/ingestion/pipeline.py) |
| PDF → Markdown | [src/agentic_backend/ingestion/pdf_to_md.py](../../src/agentic_backend/ingestion/pdf_to_md.py) |
| LLM summariser | [src/agentic_backend/ingestion/summarizer.py](../../src/agentic_backend/ingestion/summarizer.py) |
| Document metadata builder + schema validator | [src/agentic_backend/ingestion/metadata.py](../../src/agentic_backend/ingestion/metadata.py) |
| Header + recursive chunker | [src/agentic_backend/rag/chunker.py](../../src/agentic_backend/rag/chunker.py) |
| Embedding + Chroma persistence | [src/agentic_backend/rag/vectorstore.py](../../src/agentic_backend/rag/vectorstore.py) |
| Retrieval at query time | [src/agentic_backend/rag/retriever.py](../../src/agentic_backend/rag/retriever.py) |
| Metadata schema (JSON Schema) | [src/data/knowledge_base/metadata/schema.json](../src/data/knowledge_base/metadata/schema.json) |
| Batch ingestion script (parallel) | [src/scripts/ingest_pdfs.py](../src/scripts/ingest_pdfs.py) |
| Inspector (live + reports) | [src/scripts/inspect_chroma.py](../src/scripts/inspect_chroma.py) |
| Document summariser prompt | [src/agentic_backend/llm/prompts/document_summary.txt](../../src/agentic_backend/llm/prompts/document_summary.txt) |
