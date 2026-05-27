# 🛡️ Enterprise Insurance Assistant: Agentic AI with Advanced RAG & Compliance PoC

This repository contains a production-ready Proof of Concept (PoC) for an intelligent, multi-agent Insurance Assistant. Built with an **Agentic Orchestration Backbone**, the application seamlessly integrates Retrieval-Augmented Generation (RAG) with strict regulatory compliance, enterprise guardrails, and multi-system interoperability.

The PoC runs **100% locally** on WSL2 — no external LLM API calls, no cloud dependencies.

---

## 📚 Documentation

| Doc | When to read it |
|---|---|
| **[SETUP.md](SETUP.md)** | First-time install — WSL2 prerequisites, bootstrap script, configuration, verification |
| **[USAGE.md](USAGE.md)** | Day-to-day operation — running the stack, ingesting policy PDFs, observability in Aspire, troubleshooting |
| [docs/PoC_scope.md](docs/PoC_scope.md) | Original scope & 5-phase plan |
| [docs/insurance_rag_strategic_roadmap.md](docs/insurance_rag_strategic_roadmap.md) | Strategic roadmap |

---

## 🚀 Key Features

### 1. 🤖 Multi-Agent Orchestration & Core Framework
Coordinated specialized agents over short-term (session) and long-term (cross-conversation) memory:
*   🔍 **RAG Agent** — retrieval-augmented Q&A grounded in policy documents.
*   🧭 **Supervisor** — routes each user message to RAG, Report, or polite-decline.
*   📊 **Report Agent** — extracts structured fields, renders a Markdown report with an embedded matplotlib chart.
*   ✅ **Validator** — LLM-as-judge for groundedness + citation correctness, with a 1-retry loop.

### 2. ⚖️ Responsible AI (RAI) & Compliance (EU AI Act / GDPR)
*   **Regulatory alignment** — EU AI Act record-keeping via OpenTelemetry traces; GDPR-friendly because nothing leaves the workstation.
*   **Guardrails** — supervisor declines out-of-scope requests; validator flags ungrounded answers.

### 3. 🌐 Enterprise System Integration (designed-for)
*   **Document management** — secure PDF upload → vector pipeline.
*   **Multi-user memory** — every turn keyed by `user_id`, persisted in SQLite across sessions.

### 4. ⚙️ LLM Deployment, Fine-Tuning & Cost Optimization
*   **Local inference** — Ollama serves `qwen2.5:7b` quantised. No per-token cost.
*   **Externalised prompts** — every agent prompt lives in [poc/app/llm/prompts/](poc/app/llm/prompts/), tunable without code changes.

---

## 📁 Project Structure

```text
insurance-agent-rag-poc/
├── README.md                       # this file (overview + roadmap)
├── SETUP.md                        # first-time install guide
├── USAGE.md                        # running, ingestion, observability, troubleshooting
├── LICENSE
├── .gitignore
├── docs/                           # PoC scope + strategic roadmap
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
    │   ├── observability/          # OTel tracing/logging/metrics (Phase 5)
    │   ├── utils/                  # citation helpers, shared utilities
    │   └── config.py               # pydantic-settings configuration
    │
    ├── scripts/                    # WSL2 CLI helpers
    │   ├── setup_wsl.sh            # one-shot bootstrap
    │   ├── run_all.sh              # Aspire + API + UI in one terminal
    │   ├── run_observability.sh    # Aspire Dashboard via Docker
    │   ├── run_api.sh / run_ui.sh  # individual launchers
    │   ├── ingest_pdfs.py          # PDF → ChromaDB pipeline
    │   ├── reset_stores.py         # wipe ChromaDB + SQLite
    │   └── smoke_test.py           # end-to-end verification
    │
    ├── data/                       # gitignored — PDFs, chroma_db, memory.sqlite
    └── tests/                      # unit + integration tests
```

---

## 🗺 Implementation Roadmap

Built in 5 incremental phases — all implemented. Full detail in [docs/PoC_scope.md](docs/PoC_scope.md).

| Phase | Focus | Key Modules |
|---|---|---|
| **1** ✅ | Basic RAG + streaming + citations | [poc/app/rag/](poc/app/rag/), [poc/app/agents/rag_agent.py](poc/app/agents/rag_agent.py) |
| **2** ✅ | LangGraph supervisor + validator with retry loop | [poc/app/graph/](poc/app/graph/), [poc/app/agents/validator_agent.py](poc/app/agents/validator_agent.py) |
| **3** ✅ | Reporting autonomy (Markdown + embedded charts) | [poc/app/reporting/](poc/app/reporting/), [poc/app/agents/report_agent.py](poc/app/agents/report_agent.py) |
| **4** ✅ | SQLite long-term memory + per-user conversations | [poc/app/memory/](poc/app/memory/), [poc/app/agents/memory_agent.py](poc/app/agents/memory_agent.py) |
| **5** ✅ | OpenTelemetry traces + logs + metrics (Aspire Dashboard) | [poc/app/observability/](poc/app/observability/), [poc/scripts/run_observability.sh](poc/scripts/run_observability.sh) |

### Phase 1 — Basic RAG
PyMuPDF loader (page-level documents) → RecursiveCharacterTextSplitter with page metadata preserved → Chroma persisted to disk → token-streamed answers via `/chat/stream` (NDJSON). Each citation in the UI carries a **Download PDF** link and a **View chunk** popover showing the retrieved text.

### Phase 2 — Supervisor + Validator
Compiled `StateGraph` ([poc/app/graph/builder.py](poc/app/graph/builder.py)): supervisor classifies the question (`rag` / `out_of_scope`); RAG generates an answer; validator (LLM-as-judge) returns JSON `{grounded, citations_ok, critique}`. On failure, the critique is fed back into the RAG prompt for **one** retry. After retry, the answer is shown with an `⚠ Unverified` badge if validation still fails. The Streamlit UI renders a 3-step progress stepper as `stage` events arrive.

### Phase 3 — Report Agent
Adds a third route `report`. The report agent retrieves with `k=10`, asks the LLM to extract structured fields (policy, coverage, premium, claims, exclusions) as JSON, renders a Markdown report including a matplotlib bar chart (lump-sum vs installment total) embedded inline as a base64 PNG. Reports bypass the validator. The UI stepper adapts: `Supervisor → Report` for reports, `Supervisor → RAG → Validator` for rag, `Supervisor` only for declines.

### Phase 4 — Long-Term Memory
SQLite (`conversations`, `messages`) at `poc/data/memory.sqlite` via [poc/app/memory/store.py](poc/app/memory/store.py). Every `/chat` and `/chat/stream` turn is persisted, keyed by `user_id` and `conversation_id`. RAG prepends the last 3 turns to its prompt so follow-ups stay coherent. The report agent reads the user's last 10 cross-conversation messages and renders a **User Activity** section at the top of the report. The Streamlit sidebar lists conversations with auto-generated titles; clicking a past conversation replays it from SQLite.

### Phase 5 — Observability (Aspire Dashboard)
OTel SDK wired into both the API and the UI ([poc/app/observability/tracing.py](poc/app/observability/tracing.py)). **Enabled by default** — `setup_otel()` TCP-probes `OTEL_ENDPOINT` at startup and self-disables (one-line warning) when Aspire isn't running.

What's instrumented:
- **Auto-instrumentation** of FastAPI and httpx — a request from Streamlit → API → graph nodes shows up as a single connected trace.
- **OpenInference LangChain instrumentor** — every LLM / embedding / retriever call gets a span with prompt + completion previews, model name, token usage. Langfuse-style detail in Aspire's Traces tab.
- **Manual spans** on each graph node — `supervisor.classify`, `rag.node`, `rag.reformulate`, `rag.llm.invoke`, `rag.retrieve`, `validator.judge`, `report.node`, `report.extract`, `decline.canned` — with attributes (`user.id`, `conversation.id`, `supervisor.route`, `rag.retry_count`, `validator.grounded`, etc.).
- **OTLP logs** — Python `logging` records flow to Aspire alongside the existing stderr handler, with `trace_id`/`span_id` enrichment.
- **OTLP metrics** — `rag_poc.node.invocations`, `rag_poc.node.duration` (histogram per node), `rag_poc.validator.outcomes{result=pass\|fail}`, `rag_poc.rag.chunks_retrieved`.

Backend: **Aspire Dashboard** as a single Docker container from `mcr.microsoft.com/dotnet/aspire-dashboard:9.0`. OTLP gRPC on `localhost:4317`, web UI on `http://localhost:18888`. Start it with `bash poc/scripts/run_observability.sh` (or just `run_all.sh`). `run_all.sh` recycles the container on every invocation so each run starts with empty telemetry.

---

## 🔒 Privacy Guarantee

All inference, embeddings, vector storage, and memory persistence happen on the local workstation. **No PII or policy document content is ever transmitted to a third-party LLM API.** OpenTelemetry data (span attributes, structured logs, metrics) stays inside the local Aspire container. This architecture is designed for GDPR and EU AI Act alignment from day one.
