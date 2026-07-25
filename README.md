# 🛡️ Enterprise Insurance Assistant — Agentic AI PoC

An intelligent insurance chatbot that runs **100 % locally** — no cloud APIs, no external services, no per-token cost.

Ask questions about policy documents in natural language. Get grounded answers with citations, KPI analysis, full annual reports, voice input/output, and a complete audit trail — started with one command.

---

## 🚀 Quick Start

**Requirements:** Docker Desktop (or Docker Engine + Compose plugin), 16 GB RAM, ~15 GB free disk.

```bash
git clone <your-remote-url> insurance-agent-rag-poc
cd insurance-agent-rag-poc
cp src/.env.example src/.env      # fill in APPROVAL_HMAC_SECRET (see SETUP.md)
docker compose up --build
```

Open **http://localhost:5173** — the chat UI is ready.

> **First run:** Docker downloads the language models (~7 GB) and indexes the sample PDFs. This takes 15–30 minutes. Every subsequent start is under a minute.

For detailed prerequisites and configuration see [SETUP.md](SETUP.md).

---

## 💬 What can it do?

| Ask it… | What happens |
|---|---|
| *"What is the refund window under the 2024 policy?"* | Searches the policy PDFs, answers with the exact paragraph cited |
| *"What were total claims in Q3 2022 by channel?"* | Queries the KPI dataset, returns a table + prose summary |
| *"Give me the 2024 annual report"* | Generates a full report: on-screen Markdown + downloadable DOCX and PDF |
| *"A customer bought 10 days ago with no receipt — what should I do?"* | Multi-step answer: picks the right policy year, finds the relevant clause, cites it |
| (voice) | Speak your question; hear the answer — English and Greek both supported |

**Multi-intent questions work:** *"What's the refund window AND the 2024 renewal rate?"* returns both answers in one response, each under its own heading.

Every answer cites the exact PDF chunk it came from. Every decision is logged to a PostgreSQL audit trail and visible as OpenTelemetry traces in the Aspire Dashboard.

---

## 🌐 Service URLs

Once the stack is running:

| URL | What it is |
|---|---|
| **http://localhost:5173** | Chat UI — main entry point |
| **http://localhost:8000/docs** | API documentation (FastAPI Swagger) |
| **http://localhost:18888** | Observability dashboard (Aspire — traces, logs, metrics) |
| **http://localhost:9000** | Container management (Portainer) |

Internal services — not browser UIs, but useful when debugging:

| Port | Service |
|---|---|
| :8001 | voice-service — STT and TTS |
| :8002 | agentic-service — LangGraph pipeline |
| :8003 | rag-service — vector retrieval |
| :8004 | ingestion-service — PDF processing |
| :8005 | ChromaDB — vector store |
| :5432 | PostgreSQL — connect with DBeaver / TablePlus / psql |
| :11434 | Ollama — LLM inference (shared infra stack — started via `./start-infra.sh`, not `docker compose up`) |

---

## 📁 Project Structure

```text
insurance-agent-rag-poc/
├── docker-compose.yml              # start the whole stack: docker compose up --build
├── docker/                         # one Dockerfile per service
├── README.md                       # this file
├── SETUP.md                        # prerequisites and first-time install
├── USAGE.md                        # day-to-day operations and troubleshooting
│
├── docs/
│   ├── architecture/               # deep-dives: graph, ingestion, voice, containers
│   ├── wiki/                       # how-to guides: approval gates, voice setup, etc.
│   ├── BACKLOG.md                  # planned phases and prioritisation
│   └── insurance_rag_strategic_roadmap.md  # enterprise Azure production vision
│
└── src/
    ├── .env.example                # copy to src/.env — fill in secrets and model names
    ├── requirements/               # per-service pip requirements
    │
    ├── agentic_backend/            # shared Python backend (used across services)
    │   ├── api/                    # FastAPI routes: chat, plans, feedback, audio, admin
    │   ├── graph/                  # LangGraph pipeline: planner → orchestrator → workers
    │   ├── agents/                 # planner, assembler, RAG, data, report, validator
    │   ├── skills/                 # skill registry — add a new capability here (one file)
    │   ├── tools/                  # atomic tools: vector_search, kpi_query, audit_write …
    │   ├── rag/                    # PDF loading, chunking, embeddings, retrieval
    │   ├── data/                   # KPI dataset loader and pandas executor
    │   ├── memory/                 # PostgreSQL conversation memory
    │   ├── reporting/              # Markdown / DOCX / PDF report writers
    │   ├── audit/                  # audit-event store and middleware
    │   ├── approvals/              # human-in-the-loop plan persistence and channels
    │   ├── voice/                  # Whisper STT + Piper TTS
    │   ├── observability/          # OTel tracing, logging, metrics
    │   ├── llm/                    # Ollama client and prompt templates
    │   └── config.py               # all configuration (pydantic-settings)
    │
    ├── frontend/                   # React + Vite + TypeScript SPA
    ├── data/                       # knowledge base PDFs and KPI dataset (seed data)
    ├── scripts/                    # setup helpers, ingestion scripts, smoke tests
    └── tests/                      # unit and integration tests
```

---

## 🗺 Roadmap

Phases 1–14 are fully implemented and running in the Docker stack. Phases 15–19 are planned.

| Phase | What was built | Status |
|---|---|---|
| 1 | Basic RAG: answer policy questions with PDF citations, streamed token by token | ✅ |
| 2 | Validator agent: every answer is grounded-checked; retries once if it fails | ✅ |
| 3 | Report agent: structured policy report with embedded charts | ✅ |
| 4 | Memory: conversations persist in PostgreSQL; follow-up questions stay coherent | ✅ |
| 5 | Observability: full OpenTelemetry traces, logs, and metrics in Aspire Dashboard | ✅ |
| 6 | Document ingestion: PDF → Markdown → ChromaDB with rich per-chunk metadata | ✅ |
| 7 | Year-aware retrieval: KB covers 2020/2021/2022/2024; clarifier fires when year is ambiguous | ✅ |
| 8 | Talk-to-Data: natural-language KPI queries over the insurance dataset | ✅ |
| 9 | Executive annual report: full management report combining KPI data + RAG, downloadable as DOCX/PDF | ✅ |
| 10 | Stakeholder deck: 16-slide PPTX generated from the live app | ✅ |
| 11 | Agentic stack: Planner → Orchestrator → Workers → Skills → Tools; handles multi-intent questions | ✅ |
| 12 | Human-in-the-Loop: approval gates on plans; Telegram and UI approval channels | ✅ |
| 13 | Voice: Greek and English speech-to-text (Whisper) + text-to-speech (Piper) | ✅ |
| 14 | Microservices: 6 Docker pods, PostgreSQL, ChromaDB server mode, Portainer CE | ✅ |
| 15 | Cross-conversation planning: plans persist across sessions; resume from anywhere | 📋 planned |
| 16 | Recursive skill composition: skills spawn sub-plans mid-execution | 📋 planned |
| 17 | Full Greek support: Greek KB documents, Greek answers, Greek UI | 📋 planned |
| 18 | Enterprise governance: prompt registry, MCP Gateway, OAuth 2.0, RBAC | 📋 planned |
| 19 | Regression test suite: golden query set, RAGAS metrics, CI regression gate | 📋 planned |

For phase design details and prioritisation see [docs/BACKLOG.md](docs/BACKLOG.md).

---

## 📚 Documentation

| Document | Read it when… |
|---|---|
| [SETUP.md](SETUP.md) | First-time install — Docker prerequisites, env vars, verification steps |
| [USAGE.md](USAGE.md) | Day-to-day — running the stack, uploading PDFs, reading traces, troubleshooting |
| [docs/architecture/GRAPH.md](docs/architecture/GRAPH.md) | You want to understand the LangGraph pipeline (planner → orchestrator → workers) |
| [docs/architecture/container-orchestration.md](docs/architecture/container-orchestration.md) | You want to understand the Docker services, ports, and volumes |
| [docs/agentic.md](docs/agentic.md) | You want to extend the assistant with a new Skill or Tool |
| [docs/BACKLOG.md](docs/BACKLOG.md) | Planned phases and prioritisation |
| [docs/insurance_rag_strategic_roadmap.md](docs/insurance_rag_strategic_roadmap.md) | Enterprise Azure production architecture vision |
| [docs/presentation/deck.md](docs/presentation/deck.md) | 16-slide stakeholder deck (source of truth for the PPTX) |

---

## 🔒 Privacy

All inference, embeddings, vector storage, and memory stay on the local machine. **No document content or PII is ever sent to an external API.** OpenTelemetry data (traces, logs, metrics) stays inside the local Aspire container. Designed for GDPR and EU AI Act alignment from day one.
