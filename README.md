# 🛡️ Enterprise Insurance Assistant: Agentic AI with Advanced RAG & Compliance PoC

This repository contains a production-ready Proof of Concept (PoC) for an intelligent, multi-agent Insurance Assistant. Built with an **Agentic Orchestration Backbone**, the application seamlessly integrates Retrieval-Augmented Generation (RAG) with strict regulatory compliance, enterprise guardrails, and multi-system interoperability.

The PoC runs **100% locally** on WSL2 — no external LLM API calls, no cloud dependencies.

---

## 📚 Documentation

#### Operations

| Doc | When to read it |
|---|---|
| **[SETUP.md](SETUP.md)** | First-time install — WSL2 prerequisites, bootstrap script, configuration, verification |
| **[USAGE.md](USAGE.md)** | Day-to-day operation — running the stack, ingesting PDFs, observability in Aspire, troubleshooting |

#### Architecture

| Doc | When to read it |
|---|---|
| **[docs/architecture/GRAPH.md](docs/architecture/GRAPH.md)** | LangGraph state diagram + per-node + edge reference |
| [docs/agentic.md](docs/agentic.md) | ✅ Phase 11 — Planner · Orchestrator · Workers · Tools · Skills capability catalogue + extension playbook |
| [docs/ingestion.md](docs/ingestion.md) | Phase 6 ingestion & chunking pipeline (design + tuning) |
| [docs/agentic.md § 10](docs/agentic.md#10--legacy-phase-110-contracts) | Phase 1–10 per-node MUST/MUST-NOT contracts — appended to `docs/agentic.md` |

#### Strategic vision

| Doc | When to read it |
|---|---|
| [docs/insurance_rag_strategic_roadmap.md](docs/insurance_rag_strategic_roadmap.md) | Enterprise Azure production architecture vision — PoC coverage mapping in § 5 |

#### Presentation

| Doc | When to read it |
|---|---|
| [docs/presentation/deck.md](docs/presentation/deck.md) | 16-slide stakeholder deck (PPTX source of truth) |
| [docs/presentation/README.md](docs/presentation/README.md) | Screenshot-capture runbook for the deck |

---

## 🚀 Key Features

### 1. 🤖 Agentic Multi-Agent Orchestration (Phase 11)
Planner · Orchestrator · Workers · Skills · Tools — every turn is a small DAG workflow:
*   🗺 **Planner** (`qwen2.5:3b`) — parses any question into a typed `Plan` (DAG of Steps), handles multi-intent questions in one turn.
*   🔀 **Orchestrator** — walks the DAG via LangGraph `Send()`, parallel-dispatches ready Steps, enforces budgets.
*   ⚙️ **Workers** — thin shells that load a Skill spec and call its Tools; four families: RAG, Data, Report, Memory.
*   🧩 **Skills registry** — auto-discovered from `app/skills/`; adding a capability is one file, no graph changes.
*   🔧 **Tools** — atomic, side-effect-free functions (`vector_search`, `kpi_query`, `knowledge_base_lookup`, `clarifier_check`, `audit_write`).
*   🗂 **Assembler** — merges Step outputs under H3 headers, deduplicates citations, surfaces partial-answer badges.
*   ✅ **Validator** (legacy path) — LLM-as-judge still available inside the RAG worker for single-step turns.

### 2. ⚖️ Responsible AI (RAI) & Compliance (EU AI Act / GDPR)
*   **Regulatory alignment** — EU AI Act record-keeping via OpenTelemetry traces; GDPR-friendly because nothing leaves the workstation.
*   **Guardrails** — supervisor declines out-of-scope requests; validator flags ungrounded answers.

### 3. 🌐 Enterprise System Integration (designed-for)
*   **Document management** — secure PDF upload → vector pipeline.
*   **Multi-user memory** — every turn keyed by `user_id`, persisted in PostgreSQL across sessions.

### 4. ⚙️ LLM Deployment, Fine-Tuning & Cost Optimization
*   **Local inference** — Ollama serves `qwen2.5:7b` quantised. No per-token cost.
*   **Externalised prompts** — every agent prompt lives in [src/agentic_backend/llm/prompts/](src/agentic_backend/llm/prompts/); Skill prompts are grouped under [prompts/skills/](src/agentic_backend/llm/prompts/skills/), all tunable without code changes.

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
└── src/                            # ← all application code lives here
    ├── requirements.txt
    ├── .env.example
    ├── app/                        # main application package
    │   ├── api/                    # FastAPI backend (routes, schemas, deps)
    │   ├── graph/                  # LangGraph state machine (planner → orchestrator → worker → assembler)
    │   ├── agents/                 # Planner, Assembler + 4 worker agents (RAG, Memory, Report, Validator)
    │   ├── skills/                 # Skill registry + 5 Skill specs (Phase 11)
    │   ├── tools/                  # Atomic tool registry + 5 tools (Phase 11)
    │   ├── rag/                    # PDF loader, chunker, vector store, retriever
    │   ├── data/                   # KPI dataset loader, Operation schema, pandas executor (Phase 8)
    │   ├── memory/                 # PostgreSQL episodic memory (Phase 4)
    │   ├── reporting/              # Markdown + chart + executive annual report (Phase 3/9)
    │   ├── audit/                  # Audit-event store + middleware (Phase 7)
    │   ├── llm/                    # Ollama clients + prompt templates
    │   │   └── prompts/skills/     # Skill-specific system prompts (Phase 11)
    │   ├── observability/          # OTel tracing/logging/metrics (Phase 5)
    │   ├── utils/                  # citation helpers, shared utilities
    │   └── config.py               # pydantic-settings configuration
    │
    ├── frontend/                   # React + Vite + TypeScript SPA (Phase 12b)
    │   ├── src/                    # components, hooks, pages, API client
    │   └── dist/                   # production build (gitignored; served by FastAPI StaticFiles)
    │
    ├── scripts/                    # CLI helpers
    │   ├── setup_wsl.sh            # WSL2 Docker bootstrap
    │   ├── setup_macos.sh          # macOS Docker bootstrap
    │   ├── ingest_pdfs.py          # manual PDF → ChromaDB trigger
    │   ├── reset_stores.py         # wipe ChromaDB
    │   └── smoke_test.py           # end-to-end verification
    │
    ├── data/                       # gitignored — PDFs, chroma_data
    └── tests/                      # unit + integration tests
```

---

## 🗺 Implementation Roadmap

Phases 1–12 are implemented. Phases 13–15 are designed but not yet built.

| Phase | Focus | Key Modules |
|---|---|---|
| **1** ✅ | Basic RAG + streaming + citations | [src/agentic_backend/rag/](src/agentic_backend/rag/), [src/agentic_backend/agents/rag_agent.py](src/agentic_backend/agents/rag_agent.py) |
| **2** ✅ | LangGraph supervisor + validator with retry loop | [src/agentic_backend/graph/](src/agentic_backend/graph/), [src/agentic_backend/agents/validator_agent.py](src/agentic_backend/agents/validator_agent.py) |
| **3** ✅ | Reporting autonomy (Markdown + embedded charts) | [src/agentic_backend/reporting/](src/agentic_backend/reporting/), [src/agentic_backend/agents/report_agent.py](src/agentic_backend/agents/report_agent.py) |
| **4** ✅ | PostgreSQL long-term memory + per-user conversations | [src/agentic_backend/memory/](src/agentic_backend/memory/), [src/agentic_backend/agents/memory_agent.py](src/agentic_backend/agents/memory_agent.py) |
| **5** ✅ | OpenTelemetry traces + logs + metrics (Aspire Dashboard) | [src/agentic_backend/observability/](src/agentic_backend/observability/), [src/scripts/run_observability.sh](src/scripts/run_observability.sh) |
| **6** ✅ | Per-document ingestion pipeline: PDF → Markdown → metadata sidecar → ChromaDB. Same flow used by the batch script and the `POST /ingest` endpoint for UI uploads | [src/agentic_backend/ingestion/](src/agentic_backend/ingestion/), [src/data/knowledge_base/](src/data/knowledge_base/) |
| **7** ✅ | Year-aware retrieval (KB covers 2020/2021/2022/2024 — 2023 gap), today-aware reasoning, out-of-year fallback, clarifier node, audit-trail PostgreSQL DB | [src/agentic_backend/graph/clarifier.py](src/agentic_backend/graph/clarifier.py), [src/agentic_backend/audit/](src/agentic_backend/audit/), retriever `where_filter`. Details: [Phase 7](#phase-7--year-aware-rag-clarifier-audit-trail-) |
| **8** ✅ | Talk-to-Data agent over `insurance_kpis_2020_2024.csv` (year / period / channel / product line × 14 KPIs) — natural-language quantitative analysis with drill-down follow-ups and verifiable typed Operation JSON | [src/agentic_backend/agents/data_agent.py](src/agentic_backend/agents/data_agent.py), [src/agentic_backend/data/](src/agentic_backend/data/). Details: [Phase 8](#phase-8--talk-to-data-agent-) |
| **9** ✅ | Executive annual report for a selected year — section-by-section pipeline (collector → narrator → assemble) over the Phase 8 KPI data + Phase 1 RAG chunks. Deterministic risk-flag thresholds (no LLM-decided severity), reproducibility hash, three writers (Markdown · DOCX · PDF) | [src/agentic_backend/reporting/executive/](src/agentic_backend/reporting/executive/) · [src/agentic_backend/reporting/writers/](src/agentic_backend/reporting/writers/) · [src/agentic_backend/api/routes/reports.py](src/agentic_backend/api/routes/reports.py). Details: [Phase 9](#phase-9--executive-annual-report-) |
| **10** ✅ | PoC stakeholder deck — Markdown source of truth ([docs/presentation/deck.md](docs/presentation/deck.md)) + python-pptx builder that embeds live-app screenshots from `docs/screens/`. Renders TODO placeholders for shots not yet captured so the deck always builds. 14 slides covering problem framing, capability tour, observability, retrospective | [src/scripts/build_pptx.py](src/scripts/build_pptx.py) · [docs/presentation/](docs/presentation/). Details: [Phase 10](#phase-10--poc-presentation-deck-) |
| **11** ✅ | Agentic multi-intent stack + thumbs feedback — Planner · Orchestrator · Workers · Skills · Tools DAG replacing the Phase 1–10 supervisor→single-worker routing; `POST /feedback`; `plan_id` threaded end-to-end | [src/agentic_backend/agents/planner_agent.py](src/agentic_backend/agents/planner_agent.py) · [src/agentic_backend/graph/orchestrator.py](src/agentic_backend/graph/orchestrator.py) · [src/agentic_backend/skills/](src/agentic_backend/skills/) · [src/agentic_backend/tools/](src/agentic_backend/tools/) · [src/agentic_backend/api/routes/feedback.py](src/agentic_backend/api/routes/feedback.py). Details: [Phase 11](#phase-11--agentic-multi-intent-architecture--feedback-) |
| **12** ✅ | Human-in-the-Loop approval gates + Telegram channel — suspendable Plans, per-Step approval gates, HMAC-signed callback tokens, `ApprovalChannel` interface (Telegram · Slack · Teams pluggable) | [src/agentic_backend/approvals/](src/agentic_backend/approvals/) · [src/agentic_backend/api/routes/plans.py](src/agentic_backend/api/routes/plans.py). Details: [Phase 12](#phase-12--human-in-the-loop--telegram-channel-) |
| **13** ✅ | Multi-modal voice — local faster-whisper STT + Piper TTS as transport-layer bookends; EN/EL bilingual; React mic button + AudioPlayer; `AUDIT_RETAIN_AUDIO`; OTel spans `tool.speech_to_text` / `tool.text_to_speech`; WER correction metric | [src/agentic_backend/voice/](src/agentic_backend/voice/) · [src/agentic_backend/api/routes/audio.py](src/agentic_backend/api/routes/audio.py) · [src/frontend/src/components/VoiceInput.tsx](src/frontend/src/components/VoiceInput.tsx). Details: [Phase 13](#phase-13--multi-modal-voice-) |
| **14** ✅ | Container orchestration & microservices — decompose monolith into 6 independent pods (frontend, api-gateway, voice, agentic, rag, ingestion); PostgreSQL (psycopg2, port 5432, DBeaver-ready); ChromaDB server mode; Docker Compose + Portainer CE | [docker-compose.yml](docker-compose.yml) · [docs/architecture/container-orchestration.md](docs/architecture/container-orchestration.md) |

### Nice-to-have (not on the roadmap)

Lower-priority items that improve quality but aren't gating the PoC:

- **Table extraction from PDFs** — `pymupdf4llm` handles simple tables but complex multi-page tables sometimes render messily. Fall back to `tabula-py` or `unstructured.io` only for table-heavy docs would yield cleaner chunks for KPI-style retrieval.
- **Unit test coverage** — `tests/unit/test_imports.py` catches gross breakage. Adding focused unit tests for the pure functions (`_clean_section_title`, `_smart_join_pages`, `_parse_validation`, `chunk_metadata`) would lock the chunking + parsing logic against regressions.

### Phase 1 — Basic RAG
PyMuPDF loader (page-level documents) → RecursiveCharacterTextSplitter with page metadata preserved → Chroma persisted to disk → token-streamed answers via `/chat/stream` (NDJSON). Each citation in the UI carries a **Download PDF** link and a **View chunk** popover showing the retrieved text.

### Phase 2 — Supervisor + Validator
Compiled `StateGraph` ([src/agentic_backend/graph/builder.py](src/agentic_backend/graph/builder.py)): supervisor classifies the question (`rag` / `out_of_scope`); RAG generates an answer; validator (LLM-as-judge) returns JSON `{grounded, citations_ok, critique}`. On failure, the critique is fed back into the RAG prompt for **one** retry. After retry, the answer is shown with an `⚠ Unverified` badge if validation still fails. The React UI renders a live pipeline stepper as `stage` events arrive.

### Phase 3 — Report Agent
Adds a third route `report`. The report agent retrieves with `k=10`, asks the LLM to extract structured fields (policy, coverage, premium, claims, exclusions) as JSON, renders a Markdown report including a matplotlib bar chart (lump-sum vs installment total) embedded inline as a base64 PNG. Reports bypass the validator. The UI stepper adapts: `Supervisor → Report` for reports, `Supervisor → RAG → Validator` for rag, `Supervisor` only for declines.

### Phase 4 — Long-Term Memory
PostgreSQL (`conversations`, `messages`) via [src/agentic_backend/memory/store.py](src/agentic_backend/memory/store.py). Every `/chat` and `/chat/stream` turn is persisted, keyed by `user_id` and `conversation_id`. RAG prepends the last 3 turns to its prompt so follow-ups stay coherent. The report agent reads the user's last 10 cross-conversation messages. The React sidebar lists conversations; clicking a past conversation replays it from PostgreSQL.

### Phase 5 — Observability (Aspire Dashboard)
OTel SDK wired into both the API and the UI ([src/agentic_backend/observability/tracing.py](src/agentic_backend/observability/tracing.py)). **Enabled by default** — `setup_otel()` TCP-probes `OTEL_ENDPOINT` at startup and self-disables (one-line warning) when Aspire isn't running.

### Phase 6 — Per-document ingestion pipeline
PDF → Markdown (via `pymupdf4llm`, layout-preserving) → metadata sidecar (validated against [src/data/knowledge_base/metadata/schema.json](src/data/knowledge_base/metadata/schema.json)) → ChromaDB with rich chunk metadata. Single entry point `ingest_document(pdf_path, extra_metadata)` powers three callers: the batch script `python scripts/ingest_pdfs.py`, the smoke test, and the **`POST /ingest`** endpoint that accepts file uploads from the (upcoming) UI form. Each ingested chunk carries `title`, `year`, `keywords`, `language`, `document_category`, `source`, `page`, etc. — filterable in Aspire and queryable in the retriever.

**Chunking strategy.** One Markdown file per PDF (with `<!-- page N -->` boundary markers). `RecursiveCharacterTextSplitter` runs on the **whole** body so clauses that straddle pages stay together; per-chunk metadata records the chunk's starting page (and a `pages` list when it spans more than one).

#### Why `chunk_size=1200`, `chunk_overlap=200`

| Setting | Value | Why |
|---|---|---|
| `chunk_size` | **1200** chars | A typical "Section X — …" block from an insurance policy (a clause + its surrounding context) fits comfortably. Small enough that retrieval stays precise — chunks don't drown the embedding in unrelated text. |
| `chunk_overlap` | **200** chars (≈17 %) | Standard 15–20 % overlap. A sentence ending near a chunk boundary is re-presented in the next chunk's prefix, so retrieval still wins on it. |

Tuning knobs (single env var change in `src/.env`):

| Profile | size / overlap | When |
|---|---|---|
| Conservative | 800 / 120 | Smaller LLM context window, or you want stricter chunk-to-citation precision. More chunks total → slower retrieval. |
| **Recommended** | **1200 / 200** | Default. Tuned for insurance/legal/policy PDFs. |
| Aggressive | 1800 / 300 | Long-form regulations or reports where you want broad context per hit. Risk: noisier retrieval. |

Symptoms → action:
- "Answers miss details I know are in the doc" → chunks may be too small; bump to 1500 / 250.
- "Answers wander, include unrelated facts" → chunks may be too large; drop to 900 / 150.
- After changing, always **reset + re-ingest**: `python scripts/reset_stores.py` (ChromaDB only) + `docker compose exec postgres psql -U poc -d poc < src/scripts/sql/reset_stores.sql`, then `python scripts/ingest_pdfs.py`.

What's instrumented:
- **Auto-instrumentation** of FastAPI and httpx — a request from the React SPA → API → graph nodes shows up as a single connected trace.
- **OpenInference LangChain instrumentor** — every LLM / embedding / retriever call gets a span with prompt + completion previews, model name, token usage. Langfuse-style detail in Aspire's Traces tab.
- **Manual spans** on each graph node — `supervisor.classify`, `rag.node`, `rag.reformulate`, `rag.llm.invoke`, `rag.retrieve`, `validator.judge`, `report.node`, `report.extract`, `decline.canned` — with attributes (`user.id`, `conversation.id`, `supervisor.route`, `rag.retry_count`, `validator.grounded`, etc.).
- **OTLP logs** — Python `logging` records flow to Aspire alongside the existing stderr handler, with `trace_id`/`span_id` enrichment.
- **OTLP metrics** — `rag_poc.node.invocations`, `rag_poc.node.duration` (histogram per node), `rag_poc.validator.outcomes{result=pass\|fail}`, `rag_poc.rag.chunks_retrieved`.

Backend: **Aspire Dashboard** runs as the `aspire` container in Docker Compose (`mcr.microsoft.com/dotnet/aspire-dashboard:9.0`). OTLP gRPC on `aspire:18889` (internal), web UI on `http://localhost:18888`. Starts automatically with `docker compose up` — no separate step needed. Health routes (`/health`, `/health/services`) are excluded from OTel to reduce noise.

### Phase 7 — Year-aware RAG, Clarifier, Audit trail ✅

Folds three closely-related concerns into the existing graph: temporal awareness, year-scoped retrieval, and an auditable record of every decision.

**Functional bullets**
- **Today-aware reasoning.** `datetime.now()` is injected into `GraphState.today` at graph entry and surfaced in every system prompt so the LLM can resolve relative dates ("10 days ago" → `2026-05-22`).
- **Year-scoped retrieval.** The retriever accepts a `where_filter` forwarded to `Chroma.similarity_search(filter={"year": 2020})`. Year is extracted by a cheap regex (`\b(20\d\d)\b`) on the question, with the supervisor LLM as fallback.
- **Out-of-year fallback.** KB covers **2020 / 2021 / 2022 / 2024** — the **2023 gap** is explicit. When the requested year is outside the covered set the agent declines without retrieving and offers the nearest covered years ("I have 2022 and 2024 — which one applies?").
- **Clarifier node `clarifier.ask`.** Fourth supervisor route `needs_clarification`. Triggers: no year mentioned and history doesn't resolve one · the relevant clause differs materially across years · the year is outside the covered set. Emits one targeted question and ends the turn; the next user message re-enters the supervisor.
- **Worked example (the user's question).** *"A customer requests a refund for a product purchased 10 days ago, no receipt but shows a bank transaction. Based on the 2020 policy, what should I do?"* → supervisor extracts `target_year=2020`, `purchase_date=2026-05-22` → retriever runs with `{"year": 2020}` → validator checks no other-year content leaked in.
- **Audit trail.** PostgreSQL `audit_events` table. Schema:
    ```sql
    CREATE TABLE audit_events (
      id              INTEGER PRIMARY KEY AUTOINCREMENT,
      ts              TEXT NOT NULL,            -- ISO-8601 UTC
      conversation_id INTEGER,
      user_id         TEXT NOT NULL,
      trace_id        TEXT,                     -- OTel trace correlation
      event_type      TEXT NOT NULL,            -- supervisor.route, rag.retrieve, clarifier.ask, validator.judge, year_fallback, report.generate, ...
      payload_json    TEXT NOT NULL
    );
    ```
- **Event payload examples.**
    - `supervisor.route` → `{"route": "rag", "target_year": 2020, "resolved_today": "2026-06-01"}`
    - `rag.retrieve` → `{"chunk_ids": [...], "where": {"year": 2020}, "k": 6}`
    - `year_fallback` → `{"requested": 2023, "offered": [2022, 2024]}`
    - `clarifier.ask` → `{"reason": "year_missing", "question": "Which policy year — 2022 or 2024?"}`
    - `validator.judge` → `{"grounded": true, "citations_ok": true, "retry_count": 0}`
- **Trace correlation.** Every audit row carries the current OTel `trace_id`, so an Aspire span is one click away from its audit record and vice versa.
- **Files (new / changed).** `src/agentic_backend/graph/clarifier.py` (new) · `src/agentic_backend/graph/state.py` (+`today`, `target_year`, `clarifier_reason`) · `src/agentic_backend/graph/supervisor.py` (new routes) · `src/agentic_backend/llm/prompts/supervisor.txt` (inject `today` + covered-years list) · `src/agentic_backend/rag/retriever.py` (accept `where_filter`) · `src/agentic_backend/audit/` (new package: `store.py`, `events.py`, `middleware.py`).
- **Out of scope.** UI for the audit log (CSV export is enough for the PoC) · cross-year reformulation (Phase 8/9 concern) · backfilling audit rows for already-stored conversations.

### Phase 8 — Talk-to-Data agent ✅

Adds a fourth worker agent that answers quantitative questions over a structured KPI dataset, with drill-down follow-ups and verifiable answers.

**Functional bullets**
- **Dataset.** `src/data/knowledge_base/structured/insurance_kpis.csv` (or `.xlsx`). One row per `(year, period, channel, product_line)`. Same year coverage as the PDFs: **2020 / 2021 / 2022 / 2024**.
- **Dimensions.** `year` ∈ {2020,2021,2022,2024} · `period` ∈ {`FY`,`Q1`–`Q4`,`M01`–`M12`} · `channel` ∈ {direct, broker, bancassurance, digital} · `product_line` ∈ {auto, home, life, health, commercial}.
- **Core metrics.** `policies_in_force` (stock) · `new_policies` (flow) · `renewal_rate` (%) · `gross_written_premium` · `claims_reported` · `claims_paid` · `avg_claim_settlement_days` · `nps` · `complaints` · `fraud_cases` · `compliance_incidents` · `operating_expenses` · `digital_adoption_pct`. A `insurance_kpis.schema.json` sidecar declares units and stock-vs-flow — the executor uses it to refuse nonsensical aggregations (e.g. summing `renewal_rate` across periods).
- **New supervisor route `data`.** Triggers: question mentions a metric name (`renewal rate`, `GWP`, `NPS`, …) or a quantitative verb (`compare`, `trend`, `breakdown`, `top`, `vs`) or names a dimension value · numeric comparators (`> 10%`, `between 2020 and 2024`).
- **Three-step pipeline.** `planner LLM → Operation (JSON) → executor (hand-written pandas) → renderer`. The LLM **never** emits executable code — only a typed `Operation`. This is the safety property that makes results auditable.
- **Operation example.**
    ```json
    {
      "metric": "renewal_rate",
      "filters": {"year": [2022], "channel": ["direct"], "period": ["Q3"]},
      "group_by": ["channel"],
      "aggregation": "weighted_mean",
      "compare_to": {"year": [2024], "period": ["Q3"]}
    }
    ```
- **Executor guards.** Validates each `Operation` against the schema · rejects `sum` on rate / snapshot metrics · rejects unknown dimensions or out-of-domain values · refuses queries that cross a stock/flow boundary incorrectly.
- **Drill-down follow-ups.** The last successful `Operation` lives in `GraphState.last_data_operation`. When the supervisor routes a follow-up to `data`, the planner LLM receives the previous Operation and is prompted to **patch** it (`{...prev, "group_by": ["channel"]}`) rather than start over. This is what makes drill-down feel conversational.
- **Output rendering (every successful turn).** (1) 2–4 sentence prose answer ("In Q3 2022 the direct channel renewal rate was 84.1%, up 2.3 pp from Q3 2020.") · (2) Markdown table of underlying rows, capped to 20 rows · (3) the `Operation` JSON under a "How this was computed" expander for verification.
- **Risk register (the user flagged this as the agent most likely to backfire — explicit mitigations).**
    | Risk | Mitigation |
    |---|---|
    | LLM hallucinates a metric or dimension value | Planner output validated against schema before execution; invalid fields → clarifier question |
    | "sum NPS" / "average GWP" | Executor refuses stock/flow violations; returns an explanation, not a number |
    | Free-form pandas code injection | LLM emits only the structured Operation; executor is hand-written |
    | Misleading single-cell answer | Numeric answer always shipped with row table + Operation; UI does not allow showing just the number |
    | Drill-down loses context across turns | `last_data_operation` is patched, not replaced; UI shows inherited vs new fields |
- **Files (new / changed).** `src/agentic_backend/agents/data_agent.py` (new — planner + executor + renderer) · `src/agentic_backend/data/loader.py` (new — CSV/XLSX → typed DataFrame) · `src/agentic_backend/data/operations.py` (new — `Operation` pydantic schema) · `src/agentic_backend/data/executor.py` (new — pandas executor with guards) · `src/agentic_backend/llm/prompts/data_planner.txt` (new) · `src/agentic_backend/graph/builder.py` (wire `data` route as a terminal node, like report) · `src/agentic_backend/graph/state.py` (+`last_data_operation`, `data_table_markdown`) · `src/frontend/src/` (React SPA renders narrative + table + Operation expander) · `src/data/knowledge_base/structured/insurance_kpis.{csv,schema.json}` (new — seed data).
- **Audit coupling (with Phase 7).** Every data turn writes a `data.execute` event carrying the final `Operation`, the row count returned, and a hash of the underlying CSV at execution time — so the same answer is reproducible weeks later.
- **Out of scope.** Joining the KPI dataset against the policy PDFs (cross-source RAG + data is a Phase 9 concern) · forecasting (TimeGEN-1 is in the strategic roadmap, not this phase) · user-uploaded CSVs.

### Phase 9 — Executive Annual Report ✅

Generates a management-ready annual report for a selected year, on-screen and as a downloadable DOCX or PDF, combining the Talk-to-Data KPIs (Phase 8) with policy narrative from RAG (Phase 1).

**Functional bullets**
- **Trigger.** Supervisor sees a question like "give me the 2024 annual report" → routes to `report` with `target_year=2024` → dispatched to the executive report builder.
- **Three delivery modes.** On-screen Markdown in the chat · downloadable **DOCX** (`python-docx`) · downloadable **PDF** (`weasyprint`, HTML → PDF). Same `ReportDocument` intermediate dataclass feeds all three writers.
- **Fixed section layout (comparable across years).**
    | Section | Source | Notes |
    |---|---|---|
    | **Cover** | static + year | Title · year · generated-on date · "Generated by Insurance Assistant" |
    | **Executive summary** | LLM, grounded in §2–§6 | 4–6 sentences. Bottom line up front. |
    | **Yearly performance narrative** | KPI dataset + Phase 1 RAG | One paragraph per pillar (commercial, claims, customer, compliance). |
    | **KPI highlights** | KPI dataset | 2×4 KPI grid. Year-on-year deltas vs the previous covered year (for 2024 → vs 2022, since 2023 is the gap). |
    | **Trends & variance** | KPI dataset | 3–5 line charts: GWP, renewal rate, claims paid, NPS, digital adoption. |
    | **Risk & issue indicators** | KPI dataset + RAG | Claims pressure, settlement-day drift, complaints, fraud, compliance. Severity from deterministic thresholds, not the LLM. |
    | **Actionable recommendations** | LLM, grounded in §6 + Phase 1 RAG | 3–5 bullets. Each cites the trigger metric **and** the policy chunk supporting the action. |
    | **Appendix** | KPI dataset + chunks | Full KPI table + every policy chunk cited inline. |
- **Pipeline (extends the Phase 3 `report` route).** `report.plan → report.collect → report.narrate → report.assemble → report.render`. One LLM call **per section** rather than one giant call — bounded prompts give grounded answers and a hallucination in one section is regenerable in isolation.
- **Deterministic risk-flag thresholds (no LLM severity).** The single point of LLM-free trust in the report.
    | Indicator | Green | Amber | Red |
    |---|---|---|---|
    | `claims_pressure = claims_paid / claims_reported` | < 0.7 | 0.7 – 0.9 | > 0.9 |
    | `avg_claim_settlement_days_drift` (yoy) | < +2 | +2 – +5 | > +5 |
    | `complaints` (yoy %) | < +5 % | +5 – +15 % | > +15 % |
    | `fraud_cases` (yoy %) | < +10 % | +10 – +25 % | > +25 % |
    | `compliance_incidents` (absolute) | 0 | 1 – 2 | ≥ 3 |
- **Reproducibility.** `report_run_id = sha256(year + kpi_csv_hash + git_sha)[:12]` embedded in the footer. Same triple → same identifier, so "this is the same report that was approved last quarter" is trivially verifiable.
- **Files (new / changed).** `src/agentic_backend/reporting/executive/builder.py` (new — orchestrates plan → collect → narrate → assemble) · `src/agentic_backend/reporting/executive/sections.py` (per-section dataclasses) · `src/agentic_backend/reporting/executive/thresholds.py` (deterministic risk flags) · `src/agentic_backend/reporting/writers/{markdown,docx,pdf}_writer.py` (new) · `src/agentic_backend/agents/report_agent.py` (extended — dispatch to executive builder when `target_year` is present) · `src/agentic_backend/api/routes/reports.py` (new — `GET /reports/{year}.{docx,pdf}`) · `src/agentic_backend/llm/prompts/executive/` (new — one prompt template per section).
- **One-shot experiment (called out under Phase 10 retrospective).** Keep the section pipeline as the production path; build a one-call experimental mode behind a feature flag and compare quality on the same year. The user wants this explicitly piloted.
- **Out of scope.** Multi-year reports (one report = one year for v1) · review-and-revise loop · live data refresh (the report is a point-in-time artefact).

### Phase 10 — PoC Presentation deck ✅

Final stakeholder deliverable. A short, opinionated deck (PDF + PPTX) that explains the PoC to a non-technical reader, captures what made the work interesting, and is honest about what should be done differently next time. Hand-curated content — not auto-generated like the Phase 9 report.

**Functional bullets**
- **Two formats, one source.** Source of truth = `docs/presentation/deck.md` (Markdown). PPTX built via `src/scripts/build_pptx.py` (`python-pptx`); PDF via `soffice --headless --convert-to pdf` from the PPTX. Both artefacts land in `docs/presentation/insurance-rag-poc.{pptx,pdf}`.
- **Slide A — Problem explanation (non-technical).** For a manager or client with no engineering background.
    > *Insurance branch employees spend an outsized share of their day looking up policy clauses across years of PDFs to answer questions they receive at the counter — "is this refundable?", "is this covered?", "what does the 2020 policy say about this?". The lookups are slow, inconsistent across employees, and impossible to audit after the fact. This PoC shows an assistant that answers those questions in seconds, points to the exact paragraph in the exact PDF it used, and keeps a record of every decision so compliance can review it later. It runs entirely on a workstation — no document or customer detail leaves the building.*
    - Visual: one annotated screenshot of a chat turn with a citation popover open.
- **Slide B — What interested you?** Author's voice. Things that were genuinely fun to build.
    - **Full open solution.** Self-imposed constraint: zero paid LLM APIs. Every design choice ran through the "does this still work on a 7B local model?" filter — which is why it ended up so well-grounded.
    - **Diagram design.** [docs/architecture/GRAPH.md](docs/architecture/GRAPH.md) and the per-phase architecture sketches. Drawing the state machine before writing the code shaped what actually got built.
    - **The "View chunk" button + Download PDF.** Compliance plumbing disguised as UX — the reviewer can verify any answer by opening the chunk popover or the source PDF in two clicks.
    - **Per-document ingestion → Aspire telemetry.** Chunker / vectorstore spans land in Aspire with attributes that make chunking choices visible (sections, chunks_kept vs skipped). Crucial debugging surface — in past projects we used to back up the index nightly into Postgres just to be able to diff embeddings and verify correct indexing; here the diff lives in telemetry.
    - **A real business-output report from a 7B parameter model.** The Markdown + base64 chart format is a deliberate squeeze of a small local model into a serious deliverable shape.
- **Slide C — What you'd do differently.** Frank assessment. Two–three lines per bullet.
    - **Prioritise Talk-to-Data earlier, but guard it with UI affordances.** Quantitative answers are the highest-value thing the assistant could do for an insurance ops team, and also the easiest to get wrong. A confidently wrong percentage is worse than no agent at all. Cure: surface the underlying rows and the planner `Operation` alongside every numeric answer (this is the Phase 8 design) and add UI helpers — quick-pick dimension chips, a metric glossary — so the user is steered into well-formed questions rather than free-typing pitfalls.
    - **Migrate to a proper SPA earlier.** Streamlit was the right call for rapid PoC iteration; Phase 12b replaced it with a React + Vite + TypeScript SPA — eliminating whole-script reruns, thread-blocking approval polling, and fragile dialog semantics. Rebuilding on AG-UI instead would additionally bring a standardised streaming tool-call protocol for multi-agent UIs.
    - **Azurize the model layer.** Drop Ollama 7B for production: **GPT-5.1** as the RAG generator (substantial grounded-answer quality lift over local 7B) · **mini / nano model** for the query reformulator (sub-second latency, cheap, small task) · **GPT-5.4 / reasoning-medium** for the executive report (multi-section pipeline benefits disproportionately from a reasoning model).
    - **End-to-end report generation in a single LLM call** as a side-by-side experiment against the per-section pipeline. The challenge is getting a stable executive-grade structure out of one shot; the prize is dramatically lower latency and cost. Worth one focused spike before committing to the orchestrated pipeline as the long-term path.
- **Out of scope.** Animated transitions / video walk-through · speaker-notes export (notes live as block-comments in the source Markdown but no separate render) · CI rebuild on every commit (single make target is enough).

### Phase 11 — Agentic Multi-Intent Architecture (+ Feedback) ✅

Phase 11 upgrades the supervisor → single-worker topology to a state-of-the-art **Planner · Orchestrator · Workers · Tools · Skills** agentic stack — the kind of architecture you'd expect from a production AI platform team. **Primary deliverable:** the agentic multi-intent stack. **Secondary deliverable:** thumbs-up/down feedback support, attached to the new architecture so reviewers can score the multi-intent answers. Branch: `poc/phase-11-feedback-and-parallel`. Single PR.

#### 1 — Primary: agentic multi-intent stack

Today the graph routes each user message to ONE of four workers. *"What's the refund window AND the 2024 loss ratio?"* picks one branch and silently drops the other. The new architecture treats every turn as a small workflow planned and executed by specialised agents.

- **`Planner` agent.** One structured-output LLM call against a small fast model (`qwen2.5:3b` — full 7B reserved for workers). Reads the question + conversation context + the live **Skill registry**, emits a typed `Plan` — a DAG of `Step` objects: `{step_id, skill_name, args, depends_on: list[step_id]}`. The Planner **subsumes the Phase 1–10 supervisor's classification role** — single-intent turns are just degenerate Plans with one Step; the rest of the pipeline runs identically. A self-critique sub-call validates the plan against three rules before publishing: every `skill_name` exists, the dependency graph is acyclic, no Step needs a clarification that hasn't fired yet.
- **`Orchestrator` agent.** Walks the DAG. For every Step whose deps are satisfied, dispatches to the owning worker via LangGraph's `Send()` API — independent Steps fan out in parallel, dependent Steps wait on their parents. Maintains a per-Step result cache so dependents see **structured outputs** (not just raw text). Handles partial failure (one Step fails → orchestrator either re-plans, returns partial, or surfaces a 502-style apology) so a flaky worker doesn't kill the turn. Enforces per-turn budgets (`max_steps`, `max_tool_calls`, `max_seconds`) — overrun → graceful early-stop with whatever partial result is ready.
- **`Worker` agents.** RAG · Data · Report · Memory. Each worker is reduced to a thin shell that loads a Skill spec and invokes its prompt + tools. Workers are stateless — all per-turn state lives in the LangGraph reducer.
- **`Tools`.** Atomic, side-effect-free functions exposed via Pydantic schemas. Every tool gets its own OTel span + audit row. Initial set:
    - `vector_search(query, year_filter)` → `list[Chunk]`
    - `kpi_query(operation: Operation)` → `DataFrame`
    - `knowledge_base_lookup(doc_id, section)` → `str`
    - `clarifier_check(question)` → `ClarifierVerdict`
    - `audit_write(event_type, payload)` → `None`

    Tools are bound to the LLM via structured tool-use (`bind_tools`) — no string parsing of model output anywhere in the worker layer.
- **`Skills`.** A Skill = `{name, description, system_prompt, tools_used, input_fields}` — a reusable capability bundle. System prompts live in `app/llm/prompts/skills/`. The Skill registry is loaded at planner-time so adding a new capability (e.g. *"summarise a customer complaint"*) is one new file in `app/skills/` plus a prompt in `prompts/skills/`, not a graph refactor. Initial set: `answer-policy-question` (RAG worker) · `compute-kpi` (Data worker) · `executive-section-summary` (Report worker) · `clarify-year` · `out-of-year-fallback` · `decline` (no-LLM canned refusal for out-of-scope questions). The Planner sees `name + description + input_fields` only (**never** the system prompt) so a malicious user can't jailbreak the Planner into hijacking a worker.
- **`Assembler`.** Final node. Concatenates Step outputs under H3 headers, merges citations into a single block, normalises footnote numbering. Same `ReportDocument`-style structured-output pattern as Phase 9.

**State-of-the-art touches.**
- **Structured outputs end to end.** Pydantic at every agent boundary; no JSON-extract-from-prose.
- **Tool use via OpenAI-style function calling** (`langchain.chat_models.bind_tools` over local Ollama).
- **Streaming everywhere.** Planner emits the plan as it forms · orchestrator emits each Step's start/end · workers stream token-by-token. The UI renders live progress per Step.
- **Reflection loops.** Planner self-critiques before publishing the plan · Assembler self-critiques the final answer for citation completeness before returning.
- **Audit replay.** Every Plan / Step / Tool call is one audit row keyed by `trace_id` — reviewers can re-execute a turn deterministically from the audit log alone.
- **OTel span hierarchy.** `chat.turn` → `planner.plan` → `orchestrator.execute` → `step.<id>` → `tool.<name>`. Aspire shows the whole turn as one collapsible tree.

**Risks + mitigations.**
- *Planner adds one LLM call per turn (~200 ms uniform-pipeline tax)* → use a 3B fast model. The N=1 heuristic short-circuit + Orchestrator fast-lane stay **deferred** behind `settings.agentic.fast_path` so the uniform-topology promise (consistent OTel spans + audit rows on every turn) holds by default. See [docs/agentic.md § 8](docs/agentic.md#8--future-optimisation-n1-bypass) for the staged escape hatch if production latency ever demands it.
- *DAG bugs (cycle, missing dep)* → self-critique sub-call catches structural errors before execution; orchestrator re-validates at runtime.
- *Cross-Step dependency leaks PII into downstream prompts* → tool outputs flow through a passthrough sanitiser before becoming inputs to dependent Steps.
- *Phase 7/8/9 smoke tests will break* (new nodes + new audit rows) — **explicit smoke-test update is part of the phase, not a side effect.**
- *Skill registry sprawl* → enforce a `skills/__init__.py` registry export + Pydantic-validated metadata on every Skill.

**Out of scope (next-phase pointers).**
- Long-running plans + human-in-the-loop approvals → [Phase 12](#phase-12--human-in-the-loop--telegram-channel-).
- Multi-modal audio I/O → [Phase 13](#phase-13--multi-modal-voice-).
- Cross-conversation plans → [Phase 15](#phase-15--cross-conversation-planning-).
- Recursive Skill composition (Skills authoring sub-Skills) → [Phase 16](#phase-16--recursive-skill-composition-).
- Distributed worker execution · Skill marketplace UI / versioning / A-B comparison → no phase yet.

#### 2 — Secondary: feedback support

A thin slice attached to the new architecture so reviewers can score the multi-intent answers.

- **UI.** Thumbs row under each assistant turn that carries a `plan_id`, with an optional comment textarea.
- **API.** `POST /feedback {trace_id, plan_id, user_id, score: +1|-1, comment?}` — schema-validated, latest-wins on `(trace_id, user_id)` with an `updated_at` column for traceability.
- **Storage.** New `event_type='feedback.received'` row in the existing `audit_events` table — **no new table.** Keeps the storage surface unified per the Phase 7 audit pattern; CSV export gains `feedback_score` + `feedback_comment` columns via a JSON-extract over `payload_json`.
- **Telemetry.** OTel event `feedback.received` keyed by `trace_id` so Aspire stitches the verdict onto the original chat-turn trace.

#### Done criteria

- *"Refund window AND 2024 loss ratio?"* returns both answers under separate H3 headers in one turn, with the Plan visible in the audit log.
- Adding a new Skill is a **one-file PR** — no changes to Planner / Orchestrator / Workers.
- Every Step + Tool call appears as a span in Aspire under the parent `chat.turn` trace.
- Phase 7/8/9 smoke tests are updated to match the new topology and pass.
- A 👎 on any answer persists to `audit_events` and appears in the CSV export within the same session.

### Phase 12 — Human-in-the-Loop & Telegram channel ✅

Phase 12 turns the Phase 11 Orchestrator into a **suspendable workflow engine**: certain Steps (or whole Plans) pause for human approval before executing, and the approval round-trip happens over a messaging channel — Telegram first because it's the cheapest local-friendly option (`python-telegram-bot` + a self-hosted bot token), with Slack and Microsoft Teams as drop-in alternatives behind the same `ApprovalChannel` interface.

- **Approval-gated Steps.** Skills declare `requires_approval: bool` in their metadata. When the Orchestrator dispatches an approval-gated Step, it persists the Plan state, emits an `approval.requested` audit row, and surfaces an inline approval card in the UI **and** an actionable message on the configured channel. Reviewers approve / reject from either side; the Orchestrator resumes from the persisted Plan once a verdict arrives.
- **Telegram integration.** A bot polls for `/approve <token>` / `/reject <token> <reason>` commands. Tokens are short-lived (`exp=15min`), HMAC-signed, and one-shot — the audit log records who approved, when, from which chat-id. Channel is config-driven (`settings.approvals.channel = telegram | slack | teams | ui_only`).
- **Plan persistence.** Suspended Plans persist to a new `plans` row keyed by `plan_id`, with `state ∈ {pending, approved, rejected, expired, executing, done}` and a `resume_payload` blob (the Orchestrator's continuation state). The audit-replay story extends naturally — every state transition is one `plan.<state_change>` audit event.
- **Use cases.** *"Generate the executive annual report → pause → compliance officer approves → send to leadership"* · *"Bulk-ingest a new policy PDF → pause → legal reviews the metadata + first 3 chunks → orchestrator continues the ingestion pipeline"* · *"Customer-facing data answer flagged by Validator → pause → senior agent approves before sending"*.
- **Out of scope.** SMS / WhatsApp approval (paid carriers · regulatory hassle) · approval-chain workflows (one approver per gate in Phase 12) · push notifications via Apple/Google services.

### Phase 13 — Multi-modal voice ✅

Phase 13 adds **audio in and audio out** as first-class modalities. Customers in a branch can dictate a question and hear the answer; the architecture stays 100 % local — no cloud STT, no ElevenLabs.

- **Speech-to-text.** `faster-whisper` (CTranslate2-backed, int8 CPU, pip-installable — no native compilation). Singleton model lazy-loaded on first call; `vad_filter=True` suppresses silence. Supports `tiny` / `small` / `medium` / `large-v3` via `VOICE_STT_MODEL`.
- **Text-to-speech.** `piper-tts` (pip-installable, `.onnx` models). Per-language voice cache; two languages shipped: `en_US-lessac-medium` (English) and `el_GR-rapunzelina-low` (Greek). Voice models are downloaded once via `src/scripts/download_voice_models.sh` and never committed.
- **Bilingual UI.** React `VoiceInput` component with a mic button and an **EN / ΕΛ** language toggle. `AudioPlayer` component renders synthesized speech below each assistant message. Both components are hidden when `VOICE_ENABLED=false` — zero UI impact when the feature is off.
- **Transport-layer wiring.** Voice is wired at the API boundary, not inside the LangGraph graph. The graph receives and returns plain strings unchanged — no graph modifications were needed.
- **Audit + privacy.** Only sha256 + transcript recorded by default. `AUDIT_RETAIN_AUDIO=true` writes raw blobs to `data/audit_audio/<sha256>.wav`; the directory is tracked via `.gitkeep`, WAV files are gitignored. Privacy posture (100 % local) is unchanged.
- **OTel.** New spans `tool.speech_to_text` and `tool.text_to_speech` in Aspire with attributes `model_id`, `audio_bytes`, `latency_ms`, `language`, `audio_duration_ms`, `wav_bytes`.
- **WER correction metric.** Frontend detects when a user edits a voice-filled transcript before sending. `POST /audio/correction` computes Word Error Rate and Character Error Rate via Levenshtein and logs a `voice.correction` audit event — a passive quality signal requiring no extra user action.
- **Out of scope.** Image/vision inputs (no phase yet) · voice cloning · real-time bidirectional voice · STT streaming before transcription completes.

### Phase 14 — Container orchestration & microservices ✅

Phase 14 breaks the single FastAPI process into independently deployable service pods, adds
a shared infrastructure tier, and introduces a management platform for operating the running
stack. No new product features — pure infrastructure and packaging.

- **Service decomposition.** Six application pods — `frontend` (nginx:alpine), `api-gateway`,
  `voice-service` (STT + TTS), `agentic-service` (LangGraph), `rag-service` (ChromaDB retrieval),
  `ingestion-service` (PDF pipeline) — plus shared infrastructure: `chromadb` server, `ollama`,
  `aspire`, **Portainer CE** (Phase 14a).
- **Phase 14a — Docker Compose.** One `Dockerfile` per service in `docker/`; `docker-compose.yml`
  at repo root. Docker Compose is the **only** runtime — no native Python venv or Ollama install
  needed. Ollama is fully containerized with a named `ollama_data` volume and an `ollama-pull`
  one-shot init container that downloads models on first run. macOS overlay via
  `docker-compose.override.macos.yml` (adds `platform: linux/arm64` for Apple Silicon).
- **Phase 14b — Kubernetes + Helm** _(nice-to-have future enhancement)._ Helm chart skeleton
  drafted; not pursued — Docker Compose fully meets PoC needs. See [BACKLOG](docs/BACKLOG.md).
- **PostgreSQL (Phase 14c).** `memory`, `audit`, and `approval` stores all connect to a
  `postgres:16-alpine` container via psycopg2. Schema is created on first boot via
  `src/scripts/sql/init_schema.sql` (mounted as postgres init script). Port 5432 is
  exposed on the host for DBeaver / TablePlus / psql. Ad-hoc queries live in
  `src/scripts/sql/` — run them with:
  `docker compose exec postgres psql -U poc -d poc -f /dev/stdin < src/scripts/sql/audit_events.sql`
- **Key migrations.** ChromaDB embedded → server mode (`settings.chroma_host` toggle, one-line
  change); model files as bind mounts (`~/.ollama`, `~/.cache/huggingface`, `piper_voices`).
- **SSE streaming preserved.** `proxy_buffering off` in nginx.conf; `httpx.AsyncClient.stream()`
  + FastAPI `StreamingResponse` in `gateway_client.py` — token-by-token streaming through nginx.
- **React SPA Services tab.** Polls `GET /health/services` every 10 s; api-gateway fans out to
  all pods via `gateway_client.all_service_health()`. No Portainer/Docker socket needed.
- **Out of scope / nice-to-have.** Kubernetes + Helm (14b) · horizontal scaling of
  agentic-service (needs Redis-backed state store) · GPU scheduling · CI/CD image pipeline.
- **Architecture reference.** [`docs/architecture/container-orchestration.md`](docs/architecture/container-orchestration.md)

### Phase 15 — Cross-conversation planning 📋

Phase 15 lifts Plans from **per-turn** artefacts to **first-class memory objects** that span sessions, days, and users.

- **Plan persistence beyond a turn.** Plans land in a `plans` table (introduced in Phase 12 for HITL — same schema) but with no expiry. A user can pick up *"the 2024 annual report you were generating last Tuesday"* via a resume-token chip in the UI or `/resume <plan_id>` in chat.
- **Plan-aware memory.** The Phase 4 episodic memory module learns about Plans: rolling-summarisation includes *"currently executing Plan X · awaiting Step Y · 3 of 7 Steps complete"* so the assistant doesn't lose context across sessions.
- **Multi-user plans.** Plans can have multiple `participant` user_ids — *"compliance officer A approved Step 2, regional manager B will approve Step 3"*. ACLs enforced at the Orchestrator: a Step can only resume for a user listed in its `allowed_participants`.
- **Plan migration on schema change.** When a Skill's `input_schema` or `output_schema` evolves, persisted Plans referencing the old schema get a migration hook (Skills declare `schema_version`; orchestrator runs a registered `migrate_v{n}_to_v{n+1}` before resuming).
- **UI.** New sidebar panel: *"Your plans"* — pending · in-progress · done · expired — with a one-click resume.
- **Out of scope.** Plan branching / forking (a Plan is linear in Phase 15 even when re-planned) · cross-tenant plans (single-tenant PoC) · plan-of-plans (meta-orchestration; that's Phase 16 territory).

### Phase 16 — Recursive Skill composition 📋

Phase 16 lets a **Skill emit a sub-Plan** mid-execution — *"I need to dig deeper here, so spawn three child Skills, wait for them, fold their results back into my own output."* The Orchestrator becomes recursive.

- **Sub-Plan emission.** A Worker, mid-Step, can return a `SubPlanRequest{steps: [...], merge_strategy}` instead of a normal `StepResult`. The Orchestrator pauses the parent Step, dispatches the sub-Plan, and resumes the parent with the sub-Plan's structured results once it completes.
- **Recursion budgets.** New `max_recursion_depth` (default: 3) and shared `max_steps` / `max_tool_calls` / `max_seconds` budgets that span parent + children. Overrun → graceful early-stop, partial result. **Cycle detection** — a Step that re-emits its own `skill_name` in its sub-Plan is rejected at the orchestrator.
- **Audit + OTel.** Sub-Plans get their own `plan_id` and audit subtree; OTel renders parent → sub-Plan → child Steps as a nested span tree. Replay tools handle the recursion transparently because every `plan.emitted` row already references its parent (a new column on the `plans` table).
- **Use cases.** *"Summarise customer complaint → mid-Step the Skill realises it needs three sub-summaries, one per year mentioned in the complaint → spawn three `executive_section_summary` Skills → merge → return the umbrella summary"* · *"Generate annual report → individual section Skills each spawn their own data-quality-check sub-Plans"*.
- **Safety.** Sub-Plans pass through the **same Planner self-critique** rules as top-level Plans (no cycles, all `skill_name`s registered, no unfired clarifications). The Worker emitting a sub-Plan can't author Skills the Planner couldn't have authored.
- **Out of scope.** Skill marketplaces / Skills loaded from external sources (still strictly `app/skills/`) · cross-thread sub-Plan parallelism (still single-process) · sub-Plans that mutate the parent's `args` (immutable inputs).

---

## 🔒 Privacy Guarantee

All inference, embeddings, vector storage, and memory persistence happen on the local workstation. **No PII or policy document content is ever transmitted to a third-party LLM API.** OpenTelemetry data (span attributes, structured logs, metrics) stays inside the local Aspire container. This architecture is designed for GDPR and EU AI Act alignment from day one.
