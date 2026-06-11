# ACME Insurances — Local Agentic RAG PoC

> 🤖 **Auto-synced** from [`docs/wiki/Home.md`](https://github.com/AlexandrosPlessias/insurance-agent-rag-poc/blob/dev/docs/wiki/Home.md) on every merge to `dev` — do not edit via the wiki UI, your changes will be overwritten on the next sync.

An end-to-end Proof of Concept for an insurance branch-operator assistant that
answers policy + KPI questions in seconds, cites the exact paragraph it used,
and logs every decision for compliance review. Runs **100% locally** on WSL2 —
no document or customer detail ever leaves the workstation.

---

## 🚀 Start here

| If you want to… | Read |
|---|---|
| Install the stack on a fresh machine | [Setup](#setup) · [`SETUP.md`](../../SETUP.md) |
| Run the assistant + ingest PDFs | [Usage](#usage) · [`USAGE.md`](../../USAGE.md) |
| Understand how the agents are wired | [Architecture](#architecture) · [`GRAPH.md`](../../GRAPH.md) |
| See the stakeholder pitch | [`docs/presentation/deck.md`](../presentation/deck.md) · pre-built [`insurance-rag-poc.pptx`](../presentation/insurance-rag-poc.pptx) |
| Trace each phase of work | [Roadmap](#roadmap) · main [`README.md`](../../README.md) |

---

## 🧱 Architecture at a glance

```
                  ┌────────────────┐
                  │   Streamlit    │  Chat UI · download buttons ·
                  │     (UI)       │  trace_id pill · view-chunk popovers
                  └───────┬────────┘
                          │  HTTP
                          ▼
                  ┌────────────────┐
                  │    FastAPI     │  /chat · /ingest · /reports/{year}.{md|docx|pdf}
                  │   (Backend)    │  /audit/export · /health
                  └───────┬────────┘
                          │
                          ▼
            ┌──────────────────────────┐
            │       LangGraph          │  Supervisor → Worker → Validator
            │   (state machine)        │  with year-clarifier + out-of-year guard
            └─────┬─────────┬───────┬──┘
                  │         │       │
       RAG agent  │  Report │       │  Data agent
       (Phase 1)  │  agent  │       │  (Phase 8)
                  │ (Ph. 3/9)       │
                  ▼         ▼       ▼
            ┌──────────┐  ┌──────────────┐  ┌─────────────┐
            │ ChromaDB │  │ Executive    │  │ KPI CSV     │
            │ (Phase 6)│  │ Annual Report│  │ + schema    │
            └──────────┘  │  (Phase 9)   │  │ sidecar     │
                          └──────────────┘  └─────────────┘

  Cross-cutting:
    • OpenTelemetry → Aspire Dashboard (Phase 5)
    • SQLite audit trail + episodic memory (Phase 4 / 7)
```

**Tech stack.** Python 3.12 · LangGraph · FastAPI · Streamlit · Ollama
(`qwen2.5:7b` + `nomic-embed-text`) · ChromaDB · SQLite · OpenTelemetry +
.NET Aspire Dashboard · python-pptx · python-docx · reportlab.

Diagrams: [`docs/architecture/high_level_architecture.png`](../architecture/high_level_architecture.png) ·
[`GRAPH.md`](../../GRAPH.md) (LangGraph state machine).

---

## ⚙️ Setup

1. **WSL2 Ubuntu 22.04+** with Docker (Desktop or `docker.io`).
2. Clone the repo and run the bootstrap (installs Python deps, Ollama, models,
   Docker if missing, and pre-pulls the Aspire image):

   ```bash
   bash poc/scripts/setup_wsl.sh
   ```
3. Copy the env template:

   ```bash
   cp poc/.env.example poc/.env
   ```
4. Activate the venv and run the full stack in one terminal:

   ```bash
   cd poc && source .venv/bin/activate
   bash scripts/run_all.sh
   ```

   - UI → http://localhost:8501
   - API → http://localhost:8000
   - Aspire dashboard → http://localhost:18888

Full details + troubleshooting: [`SETUP.md`](../../SETUP.md).

---

## 🧭 Usage

| Action | How |
|---|---|
| Ask a policy question | Type in the Streamlit chat; the supervisor routes to RAG |
| Ask a quantitative question | *"What was the 2024 loss ratio by product?"* → Data agent |
| Generate the executive report | *"Generate the 2024 annual report"* → 3 download buttons (MD / DOCX / PDF) |
| Ingest a new PDF | Drag-and-drop in the UI sidebar **or** `python poc/scripts/ingest_pdfs.py` |
| Export audit trail | `python poc/scripts/audit_export.py` → CSV (PowerBI-ready) |
| Watch traces live | Open Aspire dashboard while you chat |

The **2023 gap is intentional** — the knowledge base covers 2020/2021/2022/2024,
and asking about 2023 triggers a graceful refusal *before* any LLM call to
demonstrate guard-rail behaviour.

Full guide: [`USAGE.md`](../../USAGE.md).

---

## 🛣 Roadmap

| Phase | Status | Headline |
|---|---|---|
| 1 — Basic RAG | ✅ | Vector retrieval + streaming + citations |
| 2 — Supervisor + Validator | ✅ | LangGraph orchestration, 1-retry validator loop |
| 3 — Report agent | ✅ | Markdown reports with embedded matplotlib charts |
| 4 — Long-term memory | ✅ | SQLite-backed per-user conversation memory |
| 5 — Observability | ✅ | OpenTelemetry → .NET Aspire Dashboard |
| 6 — Ingestion pipeline | ✅ | PDF → Markdown → metadata sidecar → ChromaDB |
| 7 — Year-aware RAG + clarifier + audit | ✅ | 2023-gap guard, today-aware reasoning, SQLite audit DB |
| 8 — Talk-to-Data agent | ✅ | Typed `Operation` JSON + pandas executor over a real KPI CSV |
| 9 — Executive Annual Report | ✅ | Section pipeline · 3 writers (MD/DOCX/PDF) · deterministic risk bands |
| 10 — Stakeholder deck | ✅ | `python-pptx` rendered from `deck.md`; LangGraph + Azure northstar slides |
| **11 — Agentic multi-intent (+ feedback)** | 📋 planned | **Planner · Orchestrator · Workers · Tools · Skills** stack — uniform pipeline, structured outputs, audit replay. Thumbs-feedback ships alongside. See [`docs/agentic.md`](../agentic.md). |
| **12 — Human-in-the-Loop & Telegram channel** | 📋 planned | Suspendable Plans · approval gates between Steps · Telegram bot (Slack / Teams pluggable) · `plans` table |
| **13 — Multi-modal voice** | 📋 planned | Local Whisper.cpp + Piper TTS as Tools · audio in/out in Streamlit · no cloud STT/TTS |
| **14 — Cross-conversation planning** | 📋 planned | Plans become first-class memory · resume-tokens · multi-user participants · Skill schema migration |
| **15 — Recursive Skill composition** | 📋 planned | Skills can emit sub-Plans · `max_recursion_depth` · cycle detection · nested OTel span tree |

Detailed per-phase write-ups live in the main [`README.md`](../../README.md). The Phase 11 agentic architecture is documented in depth at [`docs/agentic.md`](../agentic.md).

---

## 📚 Deep-dive index

| Doc | What it covers |
|---|---|
| [`README.md`](../../README.md) | Full project overview + per-phase functional/out-of-scope bullets |
| [`SETUP.md`](../../SETUP.md) | First-time install — WSL2 prerequisites, bootstrap, configuration, verification |
| [`USAGE.md`](../../USAGE.md) | Day-to-day operation — running, ingestion, observability, troubleshooting |
| [`GRAPH.md`](../../GRAPH.md) | LangGraph compiled state machine + per-node + edge reference |
| [`docs/agent_topology.md`](../agent_topology.md) | Per-node MUST / MUST-NOT contracts — design rationale (Phase 1–10 baseline) |
| [`docs/agentic.md`](../agentic.md) | 📋 **Phase 11** — Planner · Orchestrator · Workers · Tools · Skills capability catalogue + extension playbook |
| [`docs/ingestion.md`](../ingestion.md) | Phase 6 ingestion + chunking design + tuning |
| [`docs/insurance_rag_strategic_roadmap.md`](../insurance_rag_strategic_roadmap.md) | Strategic / long-term roadmap |
| [`docs/presentation/deck.md`](../presentation/deck.md) | 16-slide stakeholder deck (source of truth for the PPTX) |
| [`docs/presentation/README.md`](../presentation/README.md) | Screenshot-capture runbook for the deck |

---

## 🛡 Privacy posture

- 100 % local inference (Ollama) + local vector store (ChromaDB) + local
  SQLite (memory + audit).
- OpenTelemetry data stays inside the local Aspire container.
- Source paths in tracked artefacts are **project-relative** — no machine,
  user, or employer folder leaks into commits.
- Designed for GDPR + EU AI Act alignment from day one.

---

## 🤝 Contributing / extending

- Each phase lives on its own branch — `poc/phase-<N>-<slug>`. Merge into
  `dev` via squash-merge PR.
- Smoke test before opening a PR: `python poc/scripts/smoke_test.py`.
- Commit hygiene: keep the README phase section in sync with every new
  surface (UI / API / SQL / OTel).

---

## 📨 Contact

Author: Alexandros Plessias · 2026

Questions, demo requests, code review — open an issue or reach out directly.
