# 🛡️ Enterprise Insurance Assistant: Agentic AI with Advanced RAG & Compliance PoC

This repository contains a production-ready Proof of Concept (PoC) for an intelligent, multi-agent Insurance Assistant. Built with an **Agentic Orchestration Backbone**, the application seamlessly integrates Retrieval-Augmented Generation (RAG) with strict regulatory compliance, enterprise guardrails, and multi-system interoperability.

---

## 🚀 Key Features & Architecture

### 1. 🤖 Multi-Agent Orchestration & Core Framework
Powered by a state-of-the-art agentic framework, the system coordinates specialized agents utilizing short-term (session) and long-term (user history/knowledge) memory:
*   🔍 **RAG Agent:** Handles deep retrieval and aggregates information across contracts, policy documents, and internal knowledge bases.
*   💬 **"Talk to Your Data" Agent:** Translates complex data schemas, structural databases, and long memory into fluent, natural language answers.
*   📊 **Report Generation Agent:** Compiles insights from data, generates dynamic visual charts (Python DataFrames to images), and formats professional, client-ready reports.

### 2. ⚖️ Responsible AI (RAI) & Compliance (EU AI Act / GDPR)
Designed from the ground up to meet stringent corporate and legal data frameworks:
*   **Regulatory Alignment:** Out-of-the-box support for EU AI Act record-keeping and strict GDPR privacy controls.
*   **Input & Output Guardrails:** Active real-time checking for prompt injection, obfuscated inputs, and automated PII (Personally Identifiable Information) masking.

### 3. 🌐 Enterprise System Integration
The agentic backbone is equipped with tools to securely fetch and interact with existing enterprise infrastructure:
*   **Customer & IAM Data:** User permissions, authentication rights, and detailed client portfolios.
*   **Localization:** Built-in multi-lingual translation layers.
*   **Document Management:** Secure document upload capabilities processing unstructured contracts and policies into the vector pipeline.

### 4. ⚙️ LLM Deployment, Fine-Tuning & Cost Optimization
*   **Model Lifecycle Management:** Strategies mitigating model churn, localized regional deployments, and aggressive cost estimation hooks.
*   **Optimization:** Support for fine-tuning loops, state tuning, and robust error handling to guarantee deterministic adherence to insurance rules.

---

## 🚀 PoC Execution Guide

> Full architecture and phasing in [docs/PoC_scope.md](docs/PoC_scope.md). The PoC runs **100% locally** on WSL2 — no external LLM API calls, no cloud dependencies.

### 1. Prerequisites

| Requirement | Version / Notes |
|---|---|
| **Windows 11** with WSL2 enabled | `wsl --install -d Ubuntu` from PowerShell |
| **Ubuntu** (inside WSL2) | 22.04 or 24.04 |
| **Disk space** | ~10 GB free (models + dependencies + indexes) |
| **RAM** | 16 GB minimum recommended (qwen2.5:7b q4_K_M ≈ 4.7 GB resident) |
| **Python** | 3.10+ (uses your distro's `python3` — Ubuntu 22.04 = 3.10, 24.04 = 3.12) |
| **Ollama** | Installed by the bootstrap script |

### 2. One-shot bootstrap (recommended)

From the repo root **inside WSL2 Ubuntu**:

```bash
# If you cloned the repo on Windows, normalize line endings first.
# Otherwise scripts may fail with "set: pipefail: invalid option name"
# or "bad interpreter: /bin/bash^M".
sed -i 's/\r$//' poc/scripts/*.sh

chmod +x poc/scripts/*.sh
bash poc/scripts/setup_wsl.sh
```

> Always invoke with **`bash`**, not `sh` — Debian/Ubuntu `/bin/sh` is `dash` and doesn't support `pipefail`.

The scripts automatically `cd` into `poc/`, so they work from anywhere.

This will:
1. Install Python 3.11, build tools, curl, git.
2. Create a `.venv` virtual environment at `poc/.venv`.
3. Install all dependencies from [poc/requirements.txt](poc/requirements.txt).
4. Install Ollama (if not already present).
5. Pull `qwen2.5:7b` (main LLM) and `nomic-embed-text` (embeddings).

> ⏱ Model pulls download several GB — first run takes 10–20 min depending on connection.

### 3. Configuration

```bash
cd poc
cp .env.example .env
# edit .env if you want non-default ports / paths / models
```

Default settings (see [poc/.env.example](poc/.env.example)):

| Variable | Default | Purpose |
|---|---|---|
| `OLLAMA_HOST` | `http://localhost:11434` | Local Ollama daemon |
| `LLM_MODEL` | `qwen2.5:7b` | Reasoning model |
| `EMBED_MODEL` | `nomic-embed-text` | Embedding model |
| `CHROMA_PERSIST_DIR` | `poc/data/chroma_db` | Vector store on disk |
| `SQLITE_PATH` | `poc/data/memory.sqlite` | Episodic memory (Phase 4) |
| `API_PORT` | `8000` | FastAPI port |
| `UI_API_URL` | `http://localhost:8000` | Streamlit → API endpoint |

### 4. Running the stack

You need **three terminals** in WSL2 (or use `tmux`/`screen`):

| Terminal | Command | Purpose |
|---|---|---|
| 1 | `ollama serve` *(usually auto-started)* | Local LLM daemon |
| 2 | `bash poc/scripts/run_api.sh` | FastAPI backend on `:8000` |
| 3 | `bash poc/scripts/run_ui.sh` | Streamlit UI on `:8501` |

Open the UI in your Windows browser at **http://localhost:8501** (WSL2 forwards `localhost` automatically).

### 5. Quick smoke test (no PDFs needed)

The fastest way to verify everything works. The script synthesises a small fake auto-insurance policy PDF, ingests it, then runs 3 sample questions through the RAG agent.

```bash
cd poc && source .venv/bin/activate
python scripts/smoke_test.py
```

**Expected output** (timing varies by hardware — first run is slower because the model loads into RAM):

```
======================================================================
Phase 1 smoke test — local RAG over a synthetic insurance policy
======================================================================

11:42:03 | INFO    | smoke_test                   | Building synthetic sample PDF at .../tests/fixtures/sample_policy.pdf
11:42:03 | INFO    | app.rag.vectorstore          | Resetting Chroma collection: policies
11:42:03 | INFO    | app.rag.loader               | Loading PDF: sample_policy.pdf
11:42:03 | INFO    | app.rag.loader               |   → 3 pages with text from sample_policy.pdf
11:42:03 | INFO    | app.rag.chunker              | Chunking 3 pages (size=1000, overlap=150) ...
11:42:03 | INFO    | app.rag.chunker              |   → produced 3 chunks
11:42:03 | INFO    | app.rag.vectorstore          | Embedding + indexing 3 chunks ...
11:42:05 | INFO    | app.rag.vectorstore          |   -> indexed 3 chunks in 1.85s

----------------------------------------------------------------------
Q: What is the deductible for collision claims?
----------------------------------------------------------------------
11:42:05 | INFO    | app.agents.rag_agent         | RAG agent invoked: 'What is the deductible for collision claims?'
11:42:05 | INFO    | app.rag.retriever            | Retrieving top-5 for query: 'What is the deductible for collision claims?'
11:42:05 | INFO    | app.rag.retriever            |   → retrieved 3 chunks in 0.12s
11:42:05 | INFO    | app.agents.rag_agent         | Calling LLM with 3 context chunk(s) ...
11:42:18 | INFO    | app.agents.rag_agent         |   -> LLM responded in 12.4s
A: The deductible for collision claims is EUR 500 per claim.

Citations:
  - sample_policy.pdf (p. 1)
  - sample_policy.pdf (p. 2)
```

If you see citations pointing at the right pages, **Phase 1 is working end-to-end**. The first LLM call is slow (cold-start); subsequent calls drop to a few seconds.

### 6. Ingesting your own policy documents

Drop your PDF files into `poc/data/raw/`, then run:

```bash
cd poc && source .venv/bin/activate
python scripts/ingest_pdfs.py
```

You'll see the same log format as the smoke test — `Loading PDF`, `Chunking`, `Embedding + indexing`. The script:
1. Parses each PDF with PyMuPDF (one `Document` per page, page number kept in metadata).
2. Splits each page into ~1000-char chunks with 150-char overlap.
3. Embeds with `nomic-embed-text` and persists to `poc/data/chroma_db/`.

> ⚠ `poc/data/raw/` is **gitignored** — your policy documents never enter version control.
>
> 💡 No PDFs to hand? Try public samples — search for "sample insurance policy filetype:pdf" or use the `tests/fixtures/sample_policy.pdf` produced by `smoke_test.py`.

After ingestion, restart the API + UI (or just hit them) and ask questions about your documents in the Streamlit UI at http://localhost:8501.

### 7. Resetting local state

```bash
cd poc && source .venv/bin/activate
python scripts/reset_stores.py     # wipes ChromaDB + SQLite, keeps raw PDFs
```

### 8. Watching the flow

Every module logs to stderr with the format:

```
HH:MM:SS | LEVEL   | module.name                  | message
```

| Where logs appear | What you see |
|---|---|
| Terminal running `bash poc/scripts/run_api.sh` | `POST /chat` lines, retrieval timing, LLM call timing |
| Terminal running `python scripts/ingest_pdfs.py` | Ingestion pipeline progress |
| Terminal running `python scripts/smoke_test.py` | Full E2E flow + answers |

Adjust verbosity with the `LOG_LEVEL` env var:

```bash
LOG_LEVEL=DEBUG python scripts/smoke_test.py   # more detail
LOG_LEVEL=WARNING bash scripts/run_api.sh      # quieter API
```

---

## 📁 Project Structure

```text
insurance-agent-rag-poc/
├── README.md                       # this file
├── LICENSE
├── .gitignore
├── docs/                           # PoC scope, roadmap, architecture diagrams
│
└── poc/                            # ← all application code lives here
    ├── requirements.txt
    ├── .env.example
    ├── app/                        # main application package
    │   ├── api/                    # FastAPI backend (routes, schemas, deps)
    │   ├── ui/                     # Streamlit frontend
    │   ├── graph/                  # LangGraph supervisor + state machine
    │   ├── agents/                 # 4 worker agents (RAG, Memory, Report, Validator)
    │   ├── rag/                    # PDF loader, chunker, vector store, retriever
    │   ├── memory/                 # SQLite episodic memory (Phase 4)
    │   ├── reporting/              # Markdown + chart generation (Phase 3)
    │   ├── llm/                    # Ollama clients + prompt templates
    │   ├── observability/          # Tracing + logging (Phase 5)
    │   ├── utils/                  # citation helpers, shared utilities
    │   └── config.py               # pydantic-settings configuration
    │
    ├── scripts/                    # WSL2 CLI helpers (setup, run, ingest, reset)
    ├── data/                       # gitignored — PDFs, chroma_db, memory.sqlite
    └── tests/                      # unit + integration tests
```

---

## 🗺 Implementation Roadmap

The PoC is built in 5 incremental phases (full detail in [docs/PoC_scope.md](docs/PoC_scope.md)):

| Phase | Status | Focus | Key Modules |
|---|---|---|---|
| **1** | ✅ implemented | Basic RAG validation + streaming + citations | [poc/app/rag/](poc/app/rag/), [poc/app/agents/rag_agent.py](poc/app/agents/rag_agent.py) |
| **2** | ✅ implemented | LangGraph supervisor + validator with retry loop | [poc/app/graph/](poc/app/graph/), [poc/app/agents/validator_agent.py](poc/app/agents/validator_agent.py) |
| **3** | ✅ implemented | Reporting autonomy (Markdown + embedded charts) | [poc/app/reporting/](poc/app/reporting/), [poc/app/agents/report_agent.py](poc/app/agents/report_agent.py) |
| **4** | ✅ implemented | SQLite long-term memory + per-user conversations | [poc/app/memory/](poc/app/memory/), [poc/app/agents/memory_agent.py](poc/app/agents/memory_agent.py) |
| **5** | ✅ implemented | OpenTelemetry traces + logs (Aspire Dashboard backend) | [poc/app/observability/](poc/app/observability/), [poc/scripts/run_observability.sh](poc/scripts/run_observability.sh) |

### Phase 2 features

- **Supervisor** routes each question to `rag` (insurance / policy) or `out_of_scope` (greetings, math, unrelated).
- **Validator** uses the LLM as a judge to check groundedness + citation correctness, returning JSON `{grounded, citations_ok, critique}`.
- **Retry loop** — on validator failure the critique is fed back into the RAG prompt for one retry. After retry, the answer is shown with a `Unverified` badge if validation still fails.
- **Progress stepper** in the Streamlit UI lights up Supervisor → RAG → Validator as `stage` events arrive.
- **Externalized prompts** live in [poc/app/llm/prompts/](poc/app/llm/prompts/) (`supervisor.txt`, `rag.txt`, `reformulate.txt`, `validator.txt`) — tune without touching code.

### Phase 3 features

- **Third route** `report` joins `rag` and `out_of_scope`. The supervisor recognises summary/report/breakdown intents.
- **Report agent** ([poc/app/agents/report_agent.py](poc/app/agents/report_agent.py)) retrieves with `k=10`, asks the LLM to extract structured fields as JSON (policy / coverage / premium / claims / exclusions), then builds a Markdown report.
- **Embedded charts** — [poc/app/reporting/charts.py](poc/app/reporting/charts.py) renders a matplotlib bar chart (lump-sum vs installment total) as a base64 PNG and inlines it into the Markdown via `data:image/png;base64,...`.
- **Markdown formatter** ([poc/app/reporting/markdown.py](poc/app/reporting/markdown.py)) stitches sections: policy table → coverage table → premium block (+ chart) → claims → exclusions → sources.
- **Dynamic UI stepper** adapts to the route: `Supervisor → Report` for reports, `Supervisor → RAG → Validator` for rag, just `Supervisor` for declines.
- Reports **bypass the validator** in Phase 3 — they're synthesised from structured extraction rather than free-form generation.

### Phase 4 features

- **SQLite memory store** ([poc/app/memory/](poc/app/memory/)): two tables (`conversations`, `messages`) at `poc/data/memory.sqlite`. `MemoryStore` opens a connection per method (safe under FastAPI threading).
- **Per-user conversations**: each turn is keyed by a `user_id`; conversations have auto-generated titles from the first user message.
- **API surface**: `POST /chat` and `POST /chat/stream` accept optional `user_id` + `conversation_id` and persist both turns. New `GET /conversations`, `POST /conversations`, `GET /conversations/{id}/messages`.
- **Conversational RAG**: `rag_node` and `reformulate_question` receive the last 3 turns and prepend them to the prompt — follow-up questions stay coherent.
- **Long-term memory in reports**: `report_node` reads the user's last 10 cross-conversation messages and renders them in a **User Activity** section at the top of the report.
- **Sidebar UI**: user-ID text input, clickable conversation list with auto-titles, **+ New conversation** button. Selecting a past conversation replays its messages from SQLite.

### Phase 5 features

- **OpenTelemetry SDK** wired into both the FastAPI backend and the Streamlit UI ([poc/app/observability/tracing.py](poc/app/observability/tracing.py)). **Enabled by default** — `setup_otel()` TCP-probes `OTEL_ENDPOINT` at startup and self-disables (logs a warning, returns) if the backend isn't running, so the app stays usable when you haven't started OpenObserve yet.
- **Auto-instrumentation** of FastAPI (server spans + request attributes) and httpx (client spans). A request from Streamlit → API → graph nodes shows up as a single connected trace.
- **Manual spans** on every graph node — `supervisor.classify`, `rag.node`, `rag.reformulate`, `rag.llm.invoke`, `rag.retrieve`, `validator.judge`, `report.node`, `report.extract`, `decline.canned` — with attributes (route, retry_count, chunk_count, grounded, citations_ok, durations).
- **OTLP logs** — Python `logging` records flow to the OTel backend in parallel with the existing stderr handler, with `trace_id`/`span_id` enrichment via `LoggingInstrumentor`.
- **Pluggable backend** — exporter switches between OTLP **HTTP** and **gRPC** via `OTEL_PROTOCOL` in `.env`. Two ready-to-run launchers:
  - **OpenObserve** ([poc/scripts/run_observability_native.sh](poc/scripts/run_observability_native.sh)) — single native binary in WSL (no Docker), HTTP OTLP, UI at `http://localhost:5080`. **This is the default config in [.env.example](poc/.env.example).**
  - **Aspire Dashboard** ([poc/scripts/run_observability.sh](poc/scripts/run_observability.sh)) — single Docker container, gRPC OTLP, UI at `http://localhost:18888`.
- **Sidebar link** to whichever dashboard is configured appears in the Streamlit UI when `OTEL_ENABLED=true`.

#### Enabling observability

OTel is **on by default** (`OTEL_ENABLED=true` in [.env.example](poc/.env.example)) and targets **Option A (OpenObserve)**. If the backend isn't running when the API/UI start, the SDK self-disables and logs a one-line warning — no app crash, no noisy connection retries. Just start the backend and restart the API/UI to pick it up.

Pick **one** backend — both expose traces and logs in a web UI. To use Option B (Aspire) instead, edit the relevant `OTEL_*` lines in your `.env`.

##### Option A — OpenObserve (native binary in WSL, no Docker)  ⭐ default

```bash
# 1. Download + run the OpenObserve binary (runs in foreground).
bash poc/scripts/run_observability_native.sh
```

The script prints an env block. **Paste it into `poc/.env`** (it sets `OTEL_ENABLED=true`, the HTTP endpoint, the Basic-auth header, and the UI URL):

```bash
OTEL_ENABLED=true
OTEL_PROTOCOL=http
OTEL_ENDPOINT=http://localhost:5080/api/default
OTEL_HEADERS=Authorization=Basic YWRtaW5AZXhhbXBsZS5jb206Q29tcGxleHBhc3MjMTIz
OTEL_UI_URL=http://localhost:5080
```

```bash
# 2. Reinstall deps to pick up the OTel packages.
cd poc && source .venv/bin/activate
pip install -r requirements.txt

# 3. Restart the API and UI; the sidebar links to OpenObserve.
bash scripts/run_api.sh    # terminal A
bash scripts/run_ui.sh     # terminal B
```

The binary lives in `poc/.openobserve/` (gitignored) and runs as a regular WSL process. To run it as a background service you can wrap it with `systemd-run --user`, `nohup`, or a systemd unit — for example:

```bash
nohup bash poc/scripts/run_observability_native.sh > openobserve.log 2>&1 &
```

In the OpenObserve UI:
- **Streams** → filter by `service.name = insurance-rag-poc-api` for logs.
- **Traces** → click a trace to see the supervisor → rag → validator chain with span attributes.

##### Option B — Aspire Dashboard (Docker, gRPC)

```bash
# Requires Docker on WSL.
bash poc/scripts/run_observability.sh
```

Then override the OpenObserve defaults in `poc/.env`:

```bash
OTEL_ENABLED=true
OTEL_PROTOCOL=grpc
OTEL_ENDPOINT=http://localhost:4317
OTEL_HEADERS=
OTEL_UI_URL=http://localhost:18888
```

Restart API + UI as in Option A.

##### Stopping

| Backend | Stop command |
|---|---|
| OpenObserve (foreground) | `Ctrl+C` in the script's terminal |
| OpenObserve (`nohup`) | `pkill -f openobserve` |
| Aspire Dashboard | `docker stop aspire-dashboard` |

---

## 🧰 Troubleshooting

| Symptom | Likely cause / Fix |
|---|---|
| `ollama: command not found` | Re-run `bash poc/scripts/setup_wsl.sh` or install manually: `curl -fsSL https://ollama.com/install.sh \| sh` |
| `Connection refused on :11434` | Ollama daemon not running — start it with `ollama serve` in a separate terminal |
| `bad interpreter: /bin/bash^M` or `set: pipefail: invalid option name` | CRLF line endings (from a Windows clone). Fix with `sed -i 's/\r$//' poc/scripts/*.sh` — no need for `dos2unix` |
| `sh: invalid option name` when running a script | You used `sh script.sh`. Use `bash script.sh` instead — `/bin/sh` on Ubuntu is `dash`, which lacks `pipefail` |
| `ModuleNotFoundError: No module named 'app'` | You're not in `poc/` — `cd poc` first, or use the provided `bash poc/scripts/run_*.sh` wrappers |
| Streamlit can't reach API | Check that `run_api.sh` is running and `UI_API_URL` in `.env` matches |
| Out of memory pulling `qwen2.5:7b` | Use the lighter fallback: `ollama pull llama3.1:8b` and set `LLM_MODEL=llama3.1:8b` |
| Slow first inference | Cold-start cost — Ollama loads the model into RAM on first request; subsequent calls are fast |
| OTel data not appearing in OpenObserve | Check the `OTEL_HEADERS` value matches the script's printed `Authorization=Basic ...` line; the API and UI must be restarted after editing `.env` |
| `ConnectionError` from the OTel exporter | Backend isn't running — `bash poc/scripts/run_observability_native.sh` (OpenObserve) or `bash poc/scripts/run_observability.sh` (Aspire) |
| `ModuleNotFoundError: No module named 'opentelemetry'` | `pip install -r poc/requirements.txt` again after enabling OTel for the first time |

---

## 🔒 Privacy Guarantee

All inference, embeddings, vector storage, and memory persistence happen on the local workstation. **No PII or policy document content is ever transmitted to a third-party LLM API.** This architecture is designed for GDPR and EU AI Act alignment from day one.
