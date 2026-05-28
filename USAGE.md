# Usage Guide

Day-to-day operation of the PoC. First-time install is in [SETUP.md](SETUP.md).

---

## 1. Quick start (one terminal)

```bash
bash poc/scripts/run_all.sh
```

This launches **Aspire Dashboard** (Docker) → **FastAPI** → **Streamlit** in one terminal with prefixed output (`[api]` / `[ui]`). `Ctrl+C` stops everything cleanly.

| Service | URL | Notes |
|---|---|---|
| Streamlit UI | http://localhost:8501 | Main entry point — chat with policies |
| FastAPI | http://localhost:8000 | REST + streaming; OpenAPI at `/docs` |
| Aspire Dashboard | http://localhost:18888 | OTel traces / logs / metrics |

Env knobs:

| Var | Effect |
|---|---|
| `SKIP_OBSERVABILITY=true` | Don't start Aspire (use this if `OTEL_ENABLED=false` in your `.env`) |
| `KEEP_OBSERVABILITY_DATA=true` | Reuse an already-running Aspire container instead of restarting it (default behaviour wipes telemetry on each run) |
| `API_PORT=8000` / `API_HOST=0.0.0.0` | Override the FastAPI defaults |

---

## 2. Individual scripts (multiple terminals)

If you'd rather split the processes:

| Terminal | Command | Purpose |
|---|---|---|
| 1 | `ollama serve` *(usually auto-started)* | Local LLM daemon |
| 2 | `bash poc/scripts/run_observability.sh` | Aspire Dashboard (Docker) |
| 3 | `bash poc/scripts/run_api.sh` | FastAPI backend |
| 4 | `bash poc/scripts/run_ui.sh` | Streamlit UI |

All scripts `cd` to the `poc/` root themselves, so they work from anywhere in the repo.

---

## 3. Ingesting policy documents (Phase 6)

**Pipeline in one line:** PDF → Markdown (via `pymupdf4llm`) → LLM-summarised metadata sidecar → header-aware chunks → ChromaDB. Same `ingest_document()` function powers the batch script, the smoke test, and the `POST /ingest` upload endpoint.

> 📖 **Design rationale, chunking strategy, tuning guide → [docs/ingestion.md](docs/ingestion.md).**

### Folder layout

```
poc/data/knowledge_base/
├── raw/              # source PDFs (tracked in git)
├── processed/        # one <stem>.md per document (gitignored)
└── metadata/
    ├── schema.json   # JSON Schema for the sidecars (tracked)
    └── <stem>.json   # one validated sidecar per document (gitignored)
```

### Run it

```bash
# Auto on first run via run_all.sh:
bash poc/scripts/run_all.sh
# (auto-ingests if ChromaDB is empty AND raw/ has PDFs;
#  set SKIP_AUTO_INGEST=true to skip, RESET_KNOWLEDGE=true to force re-ingest)

# Manual:
cd poc && source .venv/bin/activate
cp ~/my-policy.pdf data/knowledge_base/raw/
python scripts/ingest_pdfs.py
# (parallel by default; INGEST_WORKERS=4 tunes worker count)
```

### Programmatic / curl

```python
from pathlib import Path
from app.ingestion.pipeline import ingest_document

result = ingest_document(
    Path("poc/data/knowledge_base/raw/my-policy.pdf"),
    extra_metadata={"title": "My Auto Policy 2024", "year": 2024},
)
```

```bash
curl -F "file=@my-policy.pdf" -F "title=My Auto Policy 2024" \
     -F "year=2024" -F "keywords=auto,collision" \
     http://localhost:8000/ingest
```

### Chunk metadata at a glance

Every chunk carries: `source`, `doc_id`, `title`, `year`, `description`, `keywords`, `language`, `document_category`, `ingestion_date_time`, `h1`..`h4`, `section`, **`section_title`**. The last one is the **primary topic anchor for semantic search** — stripped of markdown formatting and leading numbering, so `## **1. Refund Policy**` and `## 1. Refund Policy` from different years both filter as `section_title = "Refund Policy"`.

```python
# Find the refund-policy chunk across every PDF:
collection.query(
    query_texts=["what's the refund window?"],
    where={"section_title": "Refund Policy"},
    n_results=5,
)
```

Full metadata table and JSON Schema in [docs/ingestion.md §7 + §9](docs/ingestion.md).

> 📁 **Tracked vs ignored under `poc/data/knowledge_base/`:**
> - `raw/*.pdf` → **tracked** in git (the four `Enhanced_Customer_Guidelines_*.pdf` samples ship with the repo). New PDFs you drop in get committed unless you add a per-file pattern to `.gitignore`.
> - `processed/*.md` → gitignored (regenerated from the PDFs).
> - `metadata/*.json` → gitignored. Only `metadata/schema.json` is tracked.

---

## 4. Observability (Aspire Dashboard)

After running `bash poc/scripts/run_all.sh`, open **http://localhost:18888**.

### Tabs

| Tab | What you see |
|---|---|
| **Structured logs** | Application logs with `trace_id` / `span_id` enrichment. Filter by `service.name = insurance-rag-poc-api` |
| **Traces** | One trace per `/chat` POST containing the full graph chain (Supervisor → RAG → Validator), HTTP spans from FastAPI, httpx client spans, and OpenInference LangChain spans with prompt / completion previews and token counts |
| **Metrics** | `rag_poc.node.invocations`, `rag_poc.node.duration`, `rag_poc.validator.outcomes`, `rag_poc.rag.chunks_retrieved` |

### Useful trace span attributes

Every node span carries:
- `user.id` and `conversation.id` — set in both `/chat` and `/chat/stream` handlers
- `supervisor.route` — `rag` / `report` / `out_of_scope`
- `rag.retry_count`, `rag.chunk_count`, `rag.has_critique`
- `validator.grounded`, `validator.citations_ok`, `validator.critique`
- `report.chunk_count`, `report.chart_present`, `report.markdown_chars`
- `llm.duration_s`, `llm.answer_chars`

### Filter examples

Find every request from a specific user:
```
user.id = "alex"
```

Find traces where validation failed:
```
validator.grounded = false
```

Find slow LLM calls:
```
llm.duration_s > 5
```

### Clearing telemetry between runs

`bash poc/scripts/run_all.sh` restarts the Aspire container by default — every run starts with empty telemetry. Set `KEEP_OBSERVABILITY_DATA=true` if you want to preserve history during iteration.

---

## 5. Inspecting the ChromaDB content

Useful when tuning chunk size or debugging retrieval.

```bash
cd poc && source .venv/bin/activate
```

### Live inspection (printed to terminal)

```bash
# Summary: total chunks + per-source counts
python scripts/inspect_chroma.py

# Page-level distribution for one document
python scripts/inspect_chroma.py --source Enhanced_Customer_Guidelines_2024.pdf

# Look at 5 sample chunks (with full metadata)
python scripts/inspect_chroma.py --sample 5 --metadata

# Dump every chunk (paginate or pipe to a file)
python scripts/inspect_chroma.py --all > /tmp/all_chunks.txt

# Run a similarity search end-to-end (top-K with citations + previews)
python scripts/inspect_chroma.py --search "What is the deductible?" --k 5
```

Quick smoke check after ingestion:

```bash
python scripts/inspect_chroma.py | head
# === ChromaDB inspector ===
#   collection : policies
#   total docs : 67
# Sources (4):
#     17 chunks  |  Enhanced_Customer_Guidelines_2020.pdf
#     ...
```

If `total docs` is 0 after running `ingest_pdfs.py`, something went wrong — re-run with `LOG_LEVEL=DEBUG` and check the API logs.

### Per-PDF inspection report (Markdown files)

Run-once: writes one Markdown report per source PDF to `poc/data/knowledge_base/reports/`. Each file contains the document-level metadata, chunk statistics (count, avg/min/median/max chars, page + section distribution), and the **full text + metadata** of every chunk. Reports are gitignored so they don't pollute commits.

```bash
# Generate reports for every PDF in the collection
python scripts/inspect_chroma.py --report

# Or just one PDF
python scripts/inspect_chroma.py --report --source Enhanced_Customer_Guidelines_2024.pdf

# Custom output directory
python scripts/inspect_chroma.py --report --report-dir /tmp/chunks
```

Sample output:

```
=== Writing per-PDF reports to .../data/knowledge_base/reports ===
  -> Enhanced_Customer_Guidelines_2020_chunks.md  (15 chunks)
  -> Enhanced_Customer_Guidelines_2021_chunks.md  (17 chunks)
  -> Enhanced_Customer_Guidelines_2022_chunks.md  (16 chunks)
  -> Enhanced_Customer_Guidelines_2024_chunks.md  (19 chunks)

Done. 4 report(s) written.
```

Open one in your editor to see, per chunk:

```markdown
### Chunk 4 - page 1  ·  Refund Policy

*1183 chars*

**Metadata:**

- `doc_id`: Enhanced_Customer_Guidelines_2024
- `h2`: 1. Refund Policy
- `page`: 1
- `section`: 1. Refund Policy
- `section_title`: Refund Policy
- `source`: Enhanced_Customer_Guidelines_2024.pdf
- `title`: Enhanced Customer Guidelines 2024
- `year`: 2024
- ...

**Content:**

​```markdown
## 1. Refund Policy

The refund policy for this year represents the culmination of …
​```
```

Use these reports to:
- Audit that chunks aren't header-only or too small after a tuning change.
- Compare section distribution across years (e.g. did the 2024 doc gain a "Loyalty Programme" section that 2020 lacks?).
- Verify that `section_title` is being populated correctly across documents before you build the semantic-search filter.

## 6. Resetting local state

```bash
cd poc && source .venv/bin/activate
python scripts/reset_stores.py      # wipes ChromaDB + SQLite memory
python scripts/ingest_pdfs.py       # re-index from raw/ (with summariser pass)
```

PDFs in `poc/data/knowledge_base/raw/` are kept (tracked in git). To start completely fresh including the venv:

```bash
rm -rf poc/.venv poc/data/chroma_db poc/data/memory.sqlite
rm -rf poc/data/knowledge_base/processed poc/data/knowledge_base/metadata/*.json
bash poc/scripts/setup_wsl.sh        # rebuild venv + redo pip install
```

---

## 6. Adjusting log verbosity

```bash
# DEBUG | INFO | WARNING | ERROR
LOG_LEVEL=DEBUG bash poc/scripts/run_all.sh
```

Logs go to **stderr** (visible in the terminal) **and** to Aspire's Structured logs tab when OTel is enabled.

---

## 7. Troubleshooting

| Symptom | Fix |
|---|---|
| `Connection refused on :11434` | Ollama daemon not running — `ollama serve` in a separate terminal, or just rerun `run_all.sh` |
| `OTel enabled but backend at http://localhost:4317 is unreachable` | Aspire not started yet. Run `bash poc/scripts/run_observability.sh` or restart with `run_all.sh`. App still works without OTel (warning is one line and harmless) |
| `address already in use` binding `:4317` | Something else owns the port. Diagnose with `sudo ss -tlnp \| grep ':4317'`. If a stray `tempo`/`loki` from an old experiment shows up: `sudo systemctl stop tempo loki; sudo systemctl disable tempo loki` |
| Streamlit can't reach API | Check `run_api.sh` is running and `UI_API_URL` in `.env` matches the API port |
| Slow first inference | Cold-start cost — Ollama loads the model into RAM on first request; subsequent calls are fast |
| First LLM call takes 30+ s | Cold start is normal on a laptop. Re-asking the same question is fast — model stays warm |
| `ModuleNotFoundError: No module named 'opentelemetry'` | Reinstall: `cd poc && source .venv/bin/activate && pip install -r requirements.txt` |
| Validator keeps marking answers as unverified | Your indexed PDFs may not contain the answer, or the model is hallucinating. Inspect the validator span's `critique` attribute in Aspire to see what went wrong |
