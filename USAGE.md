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

## 3. Ingesting your own policy documents

```bash
cd poc && source .venv/bin/activate

# 1. Drop your PDFs into poc/data/raw/
cp ~/my-policy.pdf data/raw/

# 2. Parse + chunk + embed + index
python scripts/ingest_pdfs.py
```

The script parses each PDF with PyMuPDF (one document per page, page number preserved in metadata), splits each page into ~1 000-char chunks with 150-char overlap, embeds with `nomic-embed-text`, and persists to `poc/data/chroma_db/`.

After ingestion, ask questions in the Streamlit UI — citations point at the right `(filename, page)`.

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

## 5. Resetting local state

```bash
cd poc && source .venv/bin/activate
python scripts/reset_stores.py      # wipes ChromaDB + SQLite memory
```

PDFs in `poc/data/raw/` are kept. To start completely fresh including the venv:

```bash
rm -rf poc/.venv poc/data/chroma_db poc/data/memory.sqlite
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
