# Usage Guide

Day-to-day operation of the PoC. First-time install is in [SETUP.md](SETUP.md).

---

## 1. Quick start (one terminal)

```bash
bash poc/scripts/run_all.sh
```

This launches **Aspire Dashboard** (Docker) → **FastAPI** → **React dev server** in one terminal with prefixed output (`[api]` / `[ui]`). `Ctrl+C` stops everything cleanly.

| Service | URL | Notes |
|---|---|---|
| React SPA | http://localhost:5173 | Main entry point — chat with policies |
| FastAPI | http://localhost:8000 | REST + streaming; OpenAPI at `/docs`; serves built SPA when `poc/frontend/dist/` exists |
| Aspire Dashboard | http://localhost:18888 | OTel traces / logs / metrics |

Env knobs:

| Var | Effect |
|---|---|
| `SKIP_OBSERVABILITY=true` | Don't start Aspire (use this if `OTEL_ENABLED=false` in your `.env`) |
| `KEEP_OBSERVABILITY_DATA=true` | Reuse an already-running Aspire container instead of restarting it (default behaviour wipes telemetry on each run) |
| `SKIP_AUTO_INGEST=true` | Skip the knowledge-base probe on startup (saves 10–30 s once the KB is already ingested) |
| `API_PORT=8000` / `API_HOST=0.0.0.0` | Override the FastAPI defaults |

> **Fast daily restart** — once the knowledge base is ingested and you don't need
> Aspire for the session, cut cold-start time from ~40 s to ~5 s:
>
> ```bash
> SKIP_AUTO_INGEST=true SKIP_OBSERVABILITY=true bash poc/scripts/run_all.sh
> ```
>
> `SKIP_AUTO_INGEST=true` skips the ChromaDB cold-import probe (safe whenever
> `src/data/chroma_db/` is already populated). `SKIP_OBSERVABILITY=true` skips the
> Docker Aspire container startup (safe whenever you are not inspecting traces).

---

## 2. Individual scripts (multiple terminals)

If you'd rather split the processes:

| Terminal | Command | Purpose |
|---|---|---|
| 1 | `ollama serve` *(usually auto-started)* | Local LLM daemon |
| 2 | `bash poc/scripts/run_observability.sh` | Aspire Dashboard (Docker) |
| 3 | `bash poc/scripts/run_api.sh` | FastAPI backend |
| 4 | `cd src/frontend && npm run dev` | React dev server (http://localhost:5173) |

All scripts `cd` to the `poc/` root themselves, so they work from anywhere in the repo.

---

## 3. Ingesting policy documents (Phase 6)

**Pipeline in one line:** PDF → Markdown (via `pymupdf4llm`) → LLM-summarised metadata sidecar → header-aware chunks → ChromaDB. Same `ingest_document()` function powers the batch script, the smoke test, and the `POST /ingest` upload endpoint.

> 📖 **Design rationale, chunking strategy, tuning guide → [docs/ingestion.md](docs/ingestion.md).**

### Folder layout

```
src/data/knowledge_base/
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
cd src && source .venv/bin/activate
cp ~/my-policy.pdf data/knowledge_base/raw/
python scripts/ingest_pdfs.py
# (parallel by default; INGEST_WORKERS=4 tunes worker count)
```

### Programmatic / curl

```python
from pathlib import Path
from app.ingestion.pipeline import ingest_document

result = ingest_document(
    Path("src/data/knowledge_base/raw/my-policy.pdf"),
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

> 📁 **Tracked vs ignored under `src/data/knowledge_base/`:**
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
| **Traces** | One trace per `/chat` POST. Phase 11 topology: `chat.turn` → `planner.plan` → `orchestrator.execute` → `step.<id>` (one per Plan Step, parallel) → `assembler.merge`. HTTP spans from FastAPI, httpx client spans, and OpenInference LangChain spans with prompt / completion previews and token counts |
| **Metrics** | `rag_poc.node.invocations`, `rag_poc.node.duration`, `rag_poc.validator.outcomes`, `rag_poc.rag.chunks_retrieved` |

### Useful trace span attributes

Every node span carries:
- `user.id` and `conversation.id` — set in both `/chat` and `/chat/stream` handlers
- **Phase 11 Planner span** (`planner.plan`): `plan.plan_id`, `plan.n_steps`, `plan.rationale`
- **Phase 11 Worker spans** (`step.<id>`): `step.step_id`, `step.skill_name`, `step.status`
- **Phase 11 Assembler span** (`assembler.merge`): `assembler.partial`, `assembler.citations_count`
- `supervisor.route` — `rag` / `report` / `out_of_scope` / `needs_clarification` / `out_of_year` *(Phase 1–10 legacy path, still emitted inside worker nodes)*
- `supervisor.today`, `supervisor.covered_years`, `supervisor.target_year`, `supervisor.year_source` *(Phase 7)*
- `rag.retry_count`, `rag.chunk_count`, `rag.has_critique`, `rag.target_year` *(Phase 7)*
- `retrieve.where_filter` — present on `rag.retrieve` whenever year-scoped *(Phase 7)*
- `clarifier.reason` ∈ {`year_missing`, `year_gap`, `ambiguous_clause`} *(Phase 7)*
- `fallback.target_year`, `fallback.offered` *(Phase 7)*
- `validator.grounded`, `validator.citations_ok`, `validator.critique`
- `report.chunk_count`, `report.chart_present`, `report.markdown_chars`, `report.target_year` *(Phase 7)*
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

Find every clarifier-triggered turn (Phase 7):
```
supervisor.route = "needs_clarification"
```

Find year-fallback turns (someone asked about 2023):
```
supervisor.route = "out_of_year"
fallback.target_year = 2023
```

Find multi-step Plans (Phase 11):
```
plan.n_steps > 1
```

Find turns where the user left a thumbs-down (Phase 11):
```
event_type = "feedback.received"
```

### Clearing telemetry between runs

`bash poc/scripts/run_all.sh` restarts the Aspire container by default — every run starts with empty telemetry. Set `KEEP_OBSERVABILITY_DATA=true` if you want to preserve history during iteration.

---

## 5. Inspecting the ChromaDB content

Useful when tuning chunk size or debugging retrieval.

```bash
cd src && source .venv/bin/activate
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

# Phase 7: scope sampling / search to one policy year
python scripts/inspect_chroma.py --year 2020
python scripts/inspect_chroma.py --search "refund window" --year 2024 --k 5
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

Run-once: writes one Markdown report per source PDF to `src/data/knowledge_base/reports/`. Each file contains the document-level metadata, chunk statistics (count, avg/min/median/max chars, page + section distribution), and the **full text + metadata** of every chunk. Reports are gitignored so they don't pollute commits.

```bash
# Generate reports for every PDF in the collection
python scripts/inspect_chroma.py --report

# Or just one PDF
python scripts/inspect_chroma.py --report --source Enhanced_Customer_Guidelines_2024.pdf

# Phase 7: report only one policy year (combinable with --source)
python scripts/inspect_chroma.py --report --year 2020

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

## 6. Year-aware routing & audit trail (Phase 7)

> **Phase 11 note.** The supervisor-based routing documented below has been superseded by the Phase 11 Planner · Orchestrator · Workers · Skills architecture. The five supervisor routes still fire **inside** the worker nodes (the RAG worker still checks year coverage, the clarifier Skill still asks for a year), but the top-level graph now goes `planner → orchestrator → worker → assembler` for every turn. See [docs/agentic.md](../docs/agentic.md) for the current architecture.

### Knowledge base coverage

`settings.kb_covered_years = [2020, 2021, 2022, 2024]` (see [poc/app/config.py](poc/app/config.py)). **2023 is an intentional gap.** When the supervisor extracts a `target_year` that isn't in this list, the request short-circuits to the **out-of-year fallback** node — no retrieval, no LLM call, just a templated reply naming the nearest covered years.

### The five supervisor routes

| Route | Triggered when | Terminal? |
|---|---|---|
| `rag` | Year resolved (from the question or recent history) **and** question is about policy content | No — runs validator + 1-retry |
| `report` | Words like "summary", "report", "overview", "breakdown" | Yes |
| `out_of_scope` | Greetings, math, chit-chat, non-insurance | Yes — `decline.canned` *(Phase 11 equivalent: `decline` Skill — same canned message, no LLM call)* |
| `needs_clarification` | Question is RAG-ish but no year is mentioned and history can't resolve one | Yes — `clarifier.ask` emits one targeted question |
| `out_of_year` | A year was named but it isn't in `kb_covered_years` | Yes — `fallback.out_of_year` offers nearest covered years |

The terminal Phase 7 branches end the turn with a single assistant message; the **next** user reply re-enters the supervisor.

### Audit trail

Every routing / retrieval / validation / clarifier / fallback decision writes a typed row into `src/data/audit.sqlite` (separate file from `memory.sqlite`). Each row carries the active OTel `trace_id`, so an Aspire span is one click away from its audit record.

| `event_type` | Payload highlights |
|---|---|
| `supervisor.route` | `{route, target_year, covered_years, resolved_today, clarifier_reason}` |
| `rag.retrieve` | `{where, k, reformulated_query, sources}` |
| `rag.answer` | `{retry_count, answer_chars, duration_s, target_year}` |
| `validator.judge` | `{grounded, citations_ok, critique, retry_count, terminal}` |
| `clarifier.ask` | `{reason, question, original_question_preview, covered_years}` |
| `year_fallback` | `{requested, offered, covered_years}` |
| `report.generate` | `{target_year, chunk_count, chart_present, markdown_chars, sources}` |
| `decline.canned` | `{reason}` |
| `planner.plan` | `{plan_id, steps: [...], rationale, n_steps}` *(Phase 11)* |
| `orchestrator.step` | `{step_id, skill_name, status, latency_ms}` *(Phase 11)* |
| `feedback.received` | `{plan_id, trace_id, score, comment, user_id, updated_at}` *(Phase 11)* |

### Exporting for compliance review

```bash
cd src && source .venv/bin/activate

# Whole log → data/audit_export.csv
python scripts/audit_export.py

# One specific trace (copy the trace_id from Aspire's Traces tab)
python scripts/audit_export.py --trace-id 8d2f...e1

# Custom output file
python scripts/audit_export.py --out /tmp/q3_audit.csv
```

The CSV keeps `payload_json` as a single column so Excel / PowerBI can ingest it without per-event schemas.

### Viewing user feedback (Phase 11)

After users rate answers with the 👍 / 👎 buttons in the chat UI, each vote is stored as a `feedback.received` row in `audit.sqlite`. Use `view_feedback.py` to print a summary table:

```bash
cd src && source .venv/bin/activate

# All feedback (up to 200 rows)
python scripts/view_feedback.py

# Filter by a specific user
python scripts/view_feedback.py --user alice

# Show last N entries only
python scripts/view_feedback.py --limit 20
```

Example output:

```
--------------------------------------------------------------------
Timestamp             User               Score   Plan ID                               Conv    Comment
--------------------------------------------------------------------
2026-07-01T17:45:12   default_user       👍 +1   3f2a1b9c-48d1-4e2a-...                 42
2026-07-01T17:46:03   default_user       👎 -1   7e8c4d2a-91f0-4c3b-...                 43
--------------------------------------------------------------------

Total: 2 feedback entries — 👍 1  👎 1
```

Each row shows:
- **Timestamp** — UTC time the feedback was submitted
- **User** — the `user_id` from the chat session
- **Score** — `👍 +1` (helpful) or `👎 -1` (needs improvement)
- **Plan ID** — the Phase 11 plan that generated the answer (links to `planner.plan` audit rows)
- **Conv** — conversation ID for cross-referencing `memory.sqlite`
- **Comment** — optional free-text (not yet exposed in the UI, available via the API)

> **Note:** When OTel is enabled the `trace_id` field carries the Aspire span ID so you can jump from a feedback row directly to its trace. When OTel is disabled the `plan_id` is stored as the `trace_id` so rows remain uniquely identifiable.

### Inspecting from the SQLite shell

The `sqlite3` CLI is installed by `setup_wsl.sh` ([1/6] step). If you're on a machine where it isn't available (`Command 'sqlite3' not found`), install it with `sudo apt install sqlite3`, **or** use the Python one-liner below.

```bash
sqlite3 src/data/audit.sqlite \
  "SELECT ts, event_type, json_extract(payload_json, '$.route') AS route \
   FROM audit_events WHERE user_id = 'alex' ORDER BY id DESC LIMIT 20;"
```

Pure-Python alternative — uses the stdlib module that's always available, no apt install needed:

```bash
cd src && source .venv/bin/activate
python -c "
from app.audit import AuditStore
from app.config import settings
for r in AuditStore(settings.audit_sqlite_path).recent(limit=20):
    print(r['ts'], r['event_type'], r['payload'].get('route', ''))
"
```

Quick count per event type (Python-only):

```bash
python -c "
import sqlite3
from app.config import settings
with sqlite3.connect(settings.audit_sqlite_path) as c:
    for et, n in c.execute('SELECT event_type, COUNT(*) FROM audit_events GROUP BY event_type'):
        print(f'{n:>4}  {et}')
"
```

---

## 7. Resetting local state

```bash
cd src && source .venv/bin/activate
python scripts/reset_stores.py                  # wipes ChromaDB + memory + audit
python scripts/reset_stores.py --keep-audit     # keep audit.sqlite intact
python scripts/ingest_pdfs.py                   # re-index from raw/ (with summariser pass)
```

PDFs in `src/data/knowledge_base/raw/` are kept (tracked in git). To start completely fresh including the venv:

```bash
rm -rf poc/.venv src/data/chroma_db src/data/memory.sqlite src/data/audit.sqlite
rm -rf src/data/knowledge_base/processed src/data/knowledge_base/metadata/*.json
bash poc/scripts/setup_wsl.sh        # rebuild venv + redo pip install
```

---

## 8. Adjusting log verbosity

```bash
# DEBUG | INFO | WARNING | ERROR
LOG_LEVEL=DEBUG bash poc/scripts/run_all.sh
```

Logs go to **stderr** (visible in the terminal) **and** to Aspire's Structured logs tab when OTel is enabled.

---

## 9. Troubleshooting

| Symptom | Fix |
|---|---|
| `Connection refused on :11434` | Ollama daemon not running — `ollama serve` in a separate terminal, or just rerun `run_all.sh` |
| `OTel enabled but backend at http://localhost:4317 is unreachable` | Aspire not started yet. Run `bash poc/scripts/run_observability.sh` or restart with `run_all.sh`. App still works without OTel (warning is one line and harmless) |
| `address already in use` binding `:4317` | Something else owns the port. Diagnose with `sudo ss -tlnp \| grep ':4317'`. If a stray `tempo`/`loki` from an old experiment shows up: `sudo systemctl stop tempo loki; sudo systemctl disable tempo loki` |
| React SPA can't reach API | Check `run_api.sh` is running; in dev the Vite proxy (`/api → http://localhost:8000`) handles routing automatically |
| Slow first inference | Cold-start cost — Ollama loads the model into RAM on first request; subsequent calls are fast |
| First LLM call takes 30+ s | Cold start is normal on a laptop. Re-asking the same question is fast — model stays warm |
| `ModuleNotFoundError: No module named 'opentelemetry'` | Reinstall: `cd src && source .venv/bin/activate && pip install -r requirements.txt` |
| Validator keeps marking answers as unverified | Your indexed PDFs may not contain the answer, or the model is hallucinating. Inspect the validator span's `critique` attribute in Aspire to see what went wrong |
| Every question turns into a clarifier "which year?" prompt | Phase 7 escalates RAG-ish questions to the clarifier when no year is mentioned. Either mention a year in the question, or answer the clarifier so the next turn inherits the year from history |
| Year-fallback fires when you asked about a covered year | Check `supervisor.target_year` in the trace. Regex may have latched onto an unrelated `20xx` token in the question. If that's the case, rephrase or set the year explicitly |
| Audit DB grows large in long sessions | `python scripts/audit_export.py --out backup.csv` then delete `src/data/audit.sqlite` — it's re-created lazily on the next request |
| `address already in use` on port 8000 or 5173 | A previous session's process is still running. Find and kill it: `fuser -k 8000/tcp && fuser -k 5173/tcp` |
