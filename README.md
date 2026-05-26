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
| **3** | ⏳ pending | Reporting autonomy (Markdown + charts) | [poc/app/reporting/](poc/app/reporting/), [poc/app/agents/report_agent.py](poc/app/agents/report_agent.py) |
| **4** | ⏳ pending | SQLite long-term memory | [poc/app/memory/](poc/app/memory/), [poc/app/agents/memory_agent.py](poc/app/agents/memory_agent.py) |
| **5** | ⏳ pending | Observability (Langfuse / OTel) | [poc/app/observability/](poc/app/observability/) |

### Phase 2 features

- **Supervisor** routes each question to `rag` (insurance / policy) or `out_of_scope` (greetings, math, unrelated).
- **Validator** uses the LLM as a judge to check groundedness + citation correctness, returning JSON `{grounded, citations_ok, critique}`.
- **Retry loop** — on validator failure the critique is fed back into the RAG prompt for one retry. After retry, the answer is shown with a `Unverified` badge if validation still fails.
- **Progress stepper** in the Streamlit UI lights up Supervisor → RAG → Validator as `stage` events arrive.
- **Externalized prompts** live in [poc/app/llm/prompts/](poc/app/llm/prompts/) (`supervisor.txt`, `rag.txt`, `reformulate.txt`, `validator.txt`) — tune without touching code.

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

---

## 🔒 Privacy Guarantee

All inference, embeddings, vector storage, and memory persistence happen on the local workstation. **No PII or policy document content is ever transmitted to a third-party LLM API.** This architecture is designed for GDPR and EU AI Act alignment from day one.
