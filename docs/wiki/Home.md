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
| Understand how the agents are wired | [Architecture](#architecture) · [`GRAPH.md`](../architecture/GRAPH.md) |
| See the stakeholder pitch | [`docs/presentation/deck.md`](../presentation/deck.md) · pre-built [`insurance-rag-poc.pptx`](../presentation/insurance-rag-poc.pptx) |
| Trace each phase of work | [Roadmap](#roadmap) · main [`README.md`](../../README.md) |

---

## 🧱 Architecture at a glance

```
                  ┌────────────────┐
                  │  React SPA     │  Chat UI · plan stepper · thumbs feedback ·
                  │  (Vite + TS)   │  download buttons · view-chunk popovers ·
                  │                │  VoiceInput (mic + EN/ΕΛ) · AudioPlayer
                  └───────┬────────┘
                          │  HTTP (Vite proxy /api → :8000 in dev)
                          ▼
                  ┌────────────────┐
                  │    FastAPI     │  /chat · /feedback · /ingest
                  │   (Backend)    │  /reports/{year}.{md|docx|pdf} · /health
                  │                │  /audio/transcribe · /audio/synthesize
                  │                │  /audio/correction  (Phase 13 voice)
                  └───────┬────────┘
                          │
                          ▼
         ┌─────────────────────────────────┐
         │           LangGraph             │  Phase 11 agentic topology
         │  Planner → Orchestrator         │
         │     → [Workers] → Assembler     │
         └──┬──────────┬───────────┬───────┘
            │ Skill    │ Skill     │ Skill
            ▼          ▼           ▼
         ┌──────┐  ┌──────┐  ┌──────────┐
         │ RAG  │  │ Data │  │  Report  │  workers dispatch via Tools
         │ agent│  │ agent│  │  agent   │
         └──┬───┘  └──┬───┘  └────┬─────┘
            │         │           │
            ▼         ▼           ▼
         ChromaDB   KPI CSV   Executive
         (Phase 6)  (Ph. 8)   pipeline (Ph. 9)

  Cross-cutting:
    • OpenTelemetry → Aspire Dashboard (Phase 5)
    • PostgreSQL audit trail + episodic memory (Phase 4 / 7)
    • Skills: agentic_backend/skills/  ·  Skill prompts: agentic_backend/llm/prompts/skills/
    • Tools: agentic_backend/tools/   ·  Feedback: POST /feedback
```

**Tech stack.** Python 3.12 · LangGraph · FastAPI · React + Vite + TypeScript · Ollama
(`qwen2.5:7b` + `qwen2.5:3b` planner + `nomic-embed-text`) · ChromaDB · PostgreSQL · OpenTelemetry +
.NET Aspire Dashboard · python-pptx · python-docx · reportlab.

Diagrams: [`docs/architecture/high_level_architecture.png`](../architecture/high_level_architecture.png) ·
[`GRAPH.md`](../architecture/GRAPH.md) (LangGraph state machine).

---

## ⚙️ Setup

**Prerequisites:** Docker Desktop (WSL2 integration enabled on Windows), 16 GB RAM, 15 GB free disk.

1. Clone the repo:
   ```bash
   git clone <repo-url> && cd insurance-agent-rag-poc
   ```
2. Copy the env template and fill in secrets:
   ```bash
   cp src/.env.example src/.env
   # edit src/.env — add APPROVAL_HMAC_SECRET and optionally TELEGRAM_BOT_TOKEN
   ```
3. Start the full stack (first run downloads ~7 GB of models and indexes PDFs):
   ```bash
   docker compose up --build
   ```
   **macOS (Apple Silicon):**
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.override.macos.yml up --build
   ```

   | Service | URL |
   |---|---|
   | React SPA | http://localhost:5173 |
   | API gateway | http://localhost:8000 |
   | Aspire (OTel) | http://localhost:18888 |
   | Portainer | http://localhost:9000 |

Full details + troubleshooting: [`SETUP.md`](../../SETUP.md).

---

## 🧭 Usage

| Action | How |
|---|---|
| Ask a policy question | Type in the React SPA chat; the Planner routes to `answer-policy-question` |
| Ask a multi-intent question | *"Refund window AND 2024 loss ratio?"* — both answers in one turn under separate H3 headers |
| Ask a quantitative question | *"What was the 2024 loss ratio by product?"* → `compute-kpi` Skill → Data worker |
| Generate the executive report | *"Generate the 2024 annual report"* → `executive-section-summary` → 3 download buttons (MD / DOCX / PDF) |
| Rate an answer | Thumbs up / down row under each scored assistant turn (turns that carry a `plan_id`); stored to `audit_events` via `POST /feedback` |
| Ask an out-of-scope question | *"What is 1+1?"* or any non-insurance topic → Planner routes to the `decline` Skill; canned refusal returned in < 1 s with no LLM call |
| View feedback scores | `python src/scripts/view_feedback.py` — formatted table of all 👍/👎 votes; `--user` and `--limit` filters available |
| Ingest a new PDF | Drag-and-drop in the UI sidebar **or** `python src/scripts/ingest_pdfs.py` |
| Export audit trail | `python src/scripts/audit_export.py` → CSV (PowerBI-ready) |
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
| 4 — Long-term memory | ✅ | PostgreSQL-backed per-user conversation memory |
| 5 — Observability | ✅ | OpenTelemetry → .NET Aspire Dashboard |
| 6 — Ingestion pipeline | ✅ | PDF → Markdown → metadata sidecar → ChromaDB |
| 7 — Year-aware RAG + clarifier + audit | ✅ | 2023-gap guard, today-aware reasoning, PostgreSQL audit DB |
| 8 — Talk-to-Data agent | ✅ | Typed `Operation` JSON + pandas executor over a real KPI CSV |
| 9 — Executive Annual Report | ✅ | Section pipeline · 3 writers (MD/DOCX/PDF) · deterministic risk bands |
| 10 — Stakeholder deck | ✅ | `python-pptx` rendered from `deck.md`; LangGraph + Azure northstar slides |
| **11 — Agentic multi-intent (+ feedback)** | ✅ | **Planner · Orchestrator · Workers · Tools · Skills** stack — uniform pipeline, structured outputs, `plan_id` on every turn, thumbs-feedback, `decline` Skill for out-of-scope refusals. See [`docs/architecture/agentic-pipeline.md`](../architecture/agentic-pipeline.md). |
| **12 — Human-in-the-Loop & Telegram channel** | ✅ | Suspendable Plans · HMAC-signed approval gates between Steps · Telegram bot (Slack / Teams pluggable) · `plans` table · drill-down chips on data turns · React UX redesign |
| **13 — Multi-modal voice** | ✅ | faster-whisper STT + Piper TTS · EN/EL bilingual · React mic + AudioPlayer · `AUDIT_RETAIN_AUDIO` · OTel spans · WER correction metric. See [Voice-Integration.md](Voice-Integration.md). |
| **14 — Container orchestration** | ✅ | Decompose monolith into 6 pods · Docker Compose + Portainer CE (14a) · PostgreSQL psycopg2 + port 5432 DBeaver-ready (14c) · ChromaDB server mode. See [Container-Orchestration.md](Container-Orchestration.md). |
| **15 — Cross-conversation planning** | 📋 planned | Plans become first-class memory · resume-tokens · multi-user participants · Skill schema migration |
| **16 — Recursive Skill composition** | 📋 planned | Skills can emit sub-Plans · `max_recursion_depth` · cycle detection · nested OTel span tree |

Detailed per-phase write-ups live in the main [`README.md`](../../README.md). The Phase 11 agentic architecture is documented in depth at [`docs/architecture/agentic-pipeline.md`](../architecture/agentic-pipeline.md).

---

## 📚 Deep-dive index

#### Operations

| Doc | What it covers |
|---|---|
| [`README.md`](../../README.md) | Full project overview + per-phase functional/out-of-scope bullets |
| [`SETUP.md`](../../SETUP.md) | First-time install — WSL2 prerequisites, bootstrap, configuration, verification |
| [`USAGE.md`](../../USAGE.md) | Day-to-day operation — running, ingestion, observability, troubleshooting |

#### Architecture

| Doc | What it covers |
|---|---|
| [`architecture/GRAPH.md`](../architecture/GRAPH.md) | LangGraph compiled state machine + per-node + edge reference |
| [`architecture/agentic-pipeline.md`](../architecture/agentic-pipeline.md) | ✅ **Phase 11** — Planner · Orchestrator · Workers · Tools · Skills capability catalogue + extension playbook |
| [`architecture/design-rationale.md`](../architecture/design-rationale.md) | Why six separate nodes — design intent, MUST/MUST-NOT contracts |
| [`architecture/ingestion.md`](../architecture/ingestion.md) | Phase 6 ingestion + chunking design + tuning |
| [`architecture/voice-integration.md`](../architecture/voice-integration.md) | ✅ **Phase 13** — STT/TTS transport layer · API routes · OTel spans · WER metric · config reference |
| [`architecture/container-orchestration.md`](../architecture/container-orchestration.md) | ✅ **Phase 14** — service map · Docker Compose · PostgreSQL · SSE streaming · macOS overlay · Kubernetes+Helm (future) |
| [`architecture/agentic-pipeline.md § 10`](../architecture/agentic-pipeline.md#10--legacy-phase-110-contracts) | Phase 1–10 per-node MUST/MUST-NOT contracts |

#### Strategic vision

| Doc | What it covers |
|---|---|
| [`docs/insurance_rag_strategic_roadmap.md`](../insurance_rag_strategic_roadmap.md) | Enterprise Azure production architecture vision — PoC coverage mapping in § 5 |

#### Presentation

| Doc | What it covers |
|---|---|
| [`docs/presentation/deck.md`](../presentation/deck.md) | 16-slide stakeholder deck (source of truth for the PPTX) |
| [`docs/presentation/README.md`](../presentation/README.md) | Screenshot-capture runbook for the deck |

---

## 🛡 Privacy posture

- 100 % local inference (Ollama) + local vector store (ChromaDB) + local
  PostgreSQL (memory + audit).
- OpenTelemetry data stays inside the local Aspire container.
- Source paths in tracked artefacts are **project-relative** — no machine,
  user, or employer folder leaks into commits.
- Designed for GDPR + EU AI Act alignment from day one.

---

## 🤝 Contributing / extending

- Each phase lives on its own branch — `poc/phase-<N>-<slug>`. Merge into
  `dev` via squash-merge PR. Refactor branches use `refactor/<slug>`.
- Smoke test before opening a PR: `python src/scripts/smoke_test.py`.
- Commit hygiene: keep the README phase section in sync with every new
  surface (UI / API / SQL / OTel).

---

## 📨 Contact

Author: Alexandros Plessias · 2026

Questions, demo requests, code review — open an issue or reach out directly.
