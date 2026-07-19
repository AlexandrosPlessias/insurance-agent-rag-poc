# Usage Guide

Day-to-day operation of the PoC. First-time install is in [SETUP.md](SETUP.md).

---

## 1. Quick start

```bash
# First run (builds images + downloads models + indexes PDFs):
docker compose up --build

# macOS first run:
docker compose -f docker-compose.yml -f docker-compose.override.macos.yml up --build

# Subsequent runs (images already built, models already in volume):
docker compose up

# Stop everything:
docker compose down
```

---

## 2. Service URLs

| URL | Service | Purpose |
|---|---|---|
| http://localhost:5173 | React SPA | Main entry point — chat with policies, upload documents, give feedback |
| http://localhost:8000 | API gateway | REST + streaming; OpenAPI at `/docs` |
| http://localhost:8001 | Voice service | STT (`/audio/transcribe`) and TTS (`/audio/synthesize`) endpoints |
| http://localhost:18888 | Aspire | OTel traces, structured logs, metrics |
| http://localhost:9000 | Portainer | Container management UI — logs, stats, exec |

---

## 3. Day-to-day commands

```bash
# Stream logs for all services:
docker compose logs -f

# Stream logs for one service:
docker compose logs -f api-gateway
docker compose logs -f ingestion-service

# Restart a single service (e.g. after changing src/.env):
docker compose restart api-gateway

# Rebuild and restart a single service (e.g. after a code change):
docker compose up --build api-gateway

# Check container health:
docker compose ps
```

---

## 4. Knowledge base and ingestion

The `ingestion-service` **clears ChromaDB and re-indexes all PDFs** in
`src/data/knowledge_base/raw/` on every container start. Watch for this banner in the
logs before sending queries:

```
=== Ingestion complete — <N> chunks indexed ===
```

### Add a new PDF

Drop the PDF into `src/data/knowledge_base/raw/` and restart the ingestion service:

```bash
cp ~/my-policy.pdf src/data/knowledge_base/raw/
docker compose restart ingestion-service
```

Or upload through the UI sidebar — the file is sent to the API, saved to `raw/`, and
ingested immediately without a restart.

### Manual ingestion trigger

```bash
docker compose exec ingestion-service python scripts/ingest_pdfs.py
```

### Chunk metadata

Every chunk carries: `source`, `doc_id`, `title`, `year`, `description`, `keywords`,
`language`, `document_category`, `ingestion_date_time`, `h1`..`h4`, `section`,
`section_title`. The `section_title` field is the primary topic anchor for semantic search
— stripped of markdown formatting and leading numbers so `## **1. Refund Policy**` and
`## 1. Refund Policy` both filter as `section_title = "Refund Policy"`.

---

## 5. Observability (Aspire)

Open **http://localhost:18888** while containers are running. Telemetry is cleared each
time `docker compose down` is run.

### Tabs

| Tab | What you see |
|---|---|
| **Traces** | One trace per `/chat` POST. Topology: `chat.turn` → `planner.plan` → `orchestrator.execute` → `step.<id>` (parallel, one per plan step) → `assembler.merge`. Health-check routes are excluded |
| **Structured logs** | Application logs enriched with `trace_id` / `span_id`. Filter by `service.name = insurance-rag-poc-api` |
| **Metrics** | `rag_poc.node.invocations`, `rag_poc.node.duration`, `rag_poc.validator.outcomes`, `rag_poc.rag.chunks_retrieved` |

### Useful span attributes

Every node span carries:
- `user.id` and `conversation.id`
- **Planner span** (`planner.plan`): `plan.plan_id`, `plan.n_steps`, `plan.rationale`
- **Worker spans** (`step.<id>`): `step.step_id`, `step.skill_name`, `step.status`
- **Assembler span** (`assembler.merge`): `assembler.partial`, `assembler.citations_count`
- `supervisor.route` — `rag` / `report` / `out_of_scope` / `needs_clarification` / `out_of_year`
- `supervisor.today`, `supervisor.covered_years`, `supervisor.target_year`, `supervisor.year_source`
- `rag.retry_count`, `rag.chunk_count`, `rag.has_critique`, `rag.target_year`
- `retrieve.where_filter` — present when year-scoped
- `clarifier.reason` ∈ {`year_missing`, `year_gap`, `ambiguous_clause`}
- `fallback.target_year`, `fallback.offered`
- `validator.grounded`, `validator.citations_ok`, `validator.critique`
- `report.chunk_count`, `report.chart_present`, `report.markdown_chars`, `report.target_year`
- `llm.duration_s`, `llm.answer_chars`

### Filter examples

```
# Every request from a specific user:
user.id = "alex"

# Traces where validation failed:
validator.grounded = false

# Slow LLM calls:
llm.duration_s > 5

# Clarifier-triggered turns:
supervisor.route = "needs_clarification"

# Year-fallback turns:
supervisor.route = "out_of_year"
fallback.target_year = 2023

# Multi-step plans:
plan.n_steps > 1

# Thumbs-down turns:
event_type = "feedback.received"
```

---

## 6. Container management (Portainer)

Open **http://localhost:9000**. On first visit Portainer asks you to set an admin
password.

From the Portainer UI you can:
- View live logs for any container (Containers → select → Logs)
- Inspect CPU / memory stats per container (Containers → select → Stats)
- Open a shell inside a container (Containers → select → Console)

---

## 7. Inspecting ChromaDB

```bash
# Summary: total chunks + per-source counts
docker compose exec ingestion-service python scripts/inspect_chroma.py

# Per-source breakdown
docker compose exec ingestion-service python scripts/inspect_chroma.py \
    --source Enhanced_Customer_Guidelines_2024.pdf

# Sample 5 chunks with full metadata
docker compose exec ingestion-service python scripts/inspect_chroma.py --sample 5 --metadata

# Similarity search (top-K with citations and previews)
docker compose exec ingestion-service python scripts/inspect_chroma.py \
    --search "What is the deductible?" --k 5

# Scope to one policy year
docker compose exec ingestion-service python scripts/inspect_chroma.py \
    --search "refund window" --year 2024 --k 5

# Generate per-PDF Markdown reports (written to src/data/knowledge_base/reports/)
docker compose exec ingestion-service python scripts/inspect_chroma.py --report
```

---

## 8. Resetting state

### Wipe ChromaDB and SQLite stores

```bash
docker compose exec api-gateway python scripts/reset_stores.py
```

This wipes ChromaDB and the SQLite memory and audit databases. The
`ingestion-service` will re-index all PDFs automatically on the next restart:

```bash
docker compose restart ingestion-service
```

### Full volume reset (re-downloads models)

Only do this if you want a completely clean slate including the Ollama model weights:

```bash
docker compose down
docker volume rm insurance-agent-rag-poc_ollama_data
docker compose up --build
```

Model download will take 10–20 minutes again.

---

## 9. Voice

Voice is enabled by default in Docker. The api-gateway proxies all `/audio/*` requests to
the `voice-service` container, which handles STT (faster-whisper) and TTS (piper-tts).

| Endpoint | Method | Purpose |
|---|---|---|
| `/audio/transcribe` | POST | Upload audio → returns transcript (EN or EL) |
| `/audio/synthesize` | POST | Text → WAV audio response |
| `/audio/correction` | POST | STT post-correction WER/CER audit |

The mic button in the React SPA captures audio via `MediaRecorder` (WebM/Opus format) and
calls `/audio/transcribe`. Language selection (EN / EL) is controlled by the toggle in the
UI header.

Quick smoke checks:

```bash
# Health check — voice service:
curl http://localhost:8001/health

# TTS — synthesize a phrase and save to WAV:
curl -s -X POST http://localhost:8001/audio/synthesize \
    -H "Content-Type: application/json" \
    -d '{"text":"Insurance claim filed successfully.","language":"en"}' \
    --output /tmp/tts_test.wav && \
    echo "TTS OK — $(stat -c%s /tmp/tts_test.wav) bytes"

# STT → TTS round-trip (inside voice-service container):
docker compose exec voice-service python -c "
from agentic_backend.voice import tts, stt
wav = tts.synthesize('Policy claim filed.', language='en')
result = stt.transcribe(wav, language='en')
print('Round-trip OK:', result)
"
```

---

## 10. Adjusting log verbosity

Add `LOG_LEVEL=DEBUG` to `src/.env`, then restart:

```bash
docker compose up
```

Logs go to each container's stdout (visible via `docker compose logs -f`) and to the
Aspire Structured Logs tab when OTel is enabled.

---

## 11. Troubleshooting

| Symptom | Fix |
|---|---|
| Port already in use (5173 / 8000 / 8001 / 9000 / 18888) | Find and stop the conflicting process: `ss -tlnp \| grep :<port>` (Linux) or `lsof -i :<port>` (macOS) |
| `address already in use` on port 11434 (Ollama) | A native Ollama process is running. Stop it: `sudo systemctl stop ollama` (or `pkill ollama`). The Docker Ollama container no longer exposes port 11434 on the host — if you see this error after updating, remove `ports: - "11434:11434"` from the `ollama` service in `docker-compose.yml` |
| Model download stalled (ollama-pull) | `docker compose restart ollama-pull` — already-downloaded weights are kept in the volume |
| Container OOM-killed | Raise Docker Desktop memory limit: Settings → Resources → Memory (12 GB recommended) |
| `ChromaDB connection refused` | The `chromadb` container is still starting. Check `docker compose ps` and wait for its health check to pass |
| Portainer shows "timeout" on first visit | Portainer initialises slowly on first boot. Refresh after 30 s |
| Ingestion completes but `/chat` returns empty citations | ChromaDB volume may be on a different Docker context. Run `docker compose exec ingestion-service python scripts/inspect_chroma.py` to confirm chunk count |
| Every question triggers "which year?" clarifier | Mention a year in your question, or answer the clarifier so the next turn inherits it from history |
| Slow first inference | Cold-start cost — Ollama loads the model into RAM on the first request; subsequent calls are fast |
| React SPA shows blank page | Frontend container still building. Check `docker compose logs -f frontend`; wait for the `ready` Vite banner |
| macOS: build fails with wrong architecture | Use the override file: `docker compose -f docker-compose.yml -f docker-compose.override.macos.yml up --build` |

---

## 12. Feedback and audit

All routing, retrieval, validation, and feedback events are written to a SQLite audit
database inside the `api-gateway` container.

```bash
# Export entire audit log to CSV:
docker compose exec api-gateway python scripts/audit_export.py

# Export one trace (copy trace_id from Aspire):
docker compose exec api-gateway python scripts/audit_export.py --trace-id 8d2f...e1

# Custom output path:
docker compose exec api-gateway python scripts/audit_export.py --out /tmp/q3_audit.csv

# View thumbs-up / thumbs-down feedback summary:
docker compose exec api-gateway python scripts/view_feedback.py

# Filter feedback by user:
docker compose exec api-gateway python scripts/view_feedback.py --user alice

# Show last N entries:
docker compose exec api-gateway python scripts/view_feedback.py --limit 20
```

The CSV keeps `payload_json` as a single column so Excel / PowerBI can ingest it without
per-event schemas. The `trace_id` column links each audit row to its Aspire span.

---

## 13. Smoke tests

### Voice smoke test (safe — no data wipe)

```bash
# TTS — synthesize and check WAV size:
curl -s -X POST http://localhost:8001/audio/synthesize \
    -H "Content-Type: application/json" \
    -d '{"text":"Insurance claim filed successfully.","language":"en"}' \
    --output /tmp/tts_test.wav && \
    echo "TTS OK — $(stat -c%s /tmp/tts_test.wav) bytes"

# STT → TTS round-trip (inside voice-service):
docker compose exec voice-service python -c "
from agentic_backend.voice import tts, stt
wav = tts.synthesize('Policy claim filed.', language='en')
result = stt.transcribe(wav, language='en')
print('Round-trip OK:', result)
"

# Greek TTS:
curl -s -X POST http://localhost:8001/audio/synthesize \
    -H "Content-Type: application/json" \
    -d '{"text":"Η αξίωση εγκρίθηκε.","language":"el"}' \
    --output /tmp/tts_el.wav && \
    echo "TTS-EL OK — $(stat -c%s /tmp/tts_el.wav) bytes"
```

### RAG smoke test

In Docker, `pymupdf4llm` (for PDF parsing) lives only in `ingestion-service` and LangGraph
lives only in `agentic-service` — no single container has both. Use `--skip-ingest` to run
the RAG scenarios against data that the `ingestion-service` has already indexed:

```bash
# Step 1 — verify data is indexed (skip if ingestion-service already ran on startup):
docker compose exec ingestion-service python scripts/ingest_pdfs.py

# Step 2 — run all RAG / report / memory scenarios:
docker compose exec agentic-service python scripts/smoke_test.py --skip-ingest
```

`--skip-ingest` skips the ChromaDB wipe and PDF ingest step. The test aborts early with a
clear error if ChromaDB is empty.

> **Without `--skip-ingest`** the script also resets ChromaDB and re-ingests the seed PDF.
> This only works in a native (non-Docker) environment where both pymupdf4llm and LangGraph
> are installed in the same venv. After running natively, restart `ingestion-service` to
> re-index all PDFs: `docker compose restart ingestion-service`

### End-to-end gateway proxy check

Verifies that the api-gateway correctly proxies audio to the voice-service:

```bash
# Transcribe via the gateway (same path the UI uses):
curl -s -X POST http://localhost:8000/audio/transcribe \
    -F "language=en" \
    -F "file=@/tmp/tts_test.wav" | python3 -m json.tool
```

Expected response:
```json
{
  "transcript": "Insurance claim filed successfully.",
  "language": "en",
  "duration_ms": 1234
}
```
