# 🛡️ Enterprise Insurance Assistant: Agentic AI with Advanced RAG & Compliance PoC

This repository contains a production-ready Proof of Concept (PoC) for an intelligent, multi-agent Insurance Assistant. Built with an **Agentic Orchestration Backbone**, the application seamlessly integrates Retrieval-Augmented Generation (RAG) with strict regulatory compliance, enterprise guardrails, and multi-system interoperability.

The PoC runs **100% locally** on WSL2 — no external LLM API calls, no cloud dependencies.

---

## 📚 Documentation

| Doc | When to read it |
|---|---|
| **[SETUP.md](SETUP.md)** | First-time install — WSL2 prerequisites, bootstrap script, configuration, verification |
| **[USAGE.md](USAGE.md)** | Day-to-day operation — running the stack, ingesting policy PDFs, observability in Aspire, troubleshooting |
| **[GRAPH.md](GRAPH.md)** | LangGraph state diagram + per-node + edge reference |
| [docs/ingestion.md](docs/ingestion.md) | Phase 6 ingestion & chunking pipeline (design + tuning) |
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

Phases 1–6 are implemented. Phases 7–10 are designed (one MD per phase) but not yet built.

| Phase | Focus | Key Modules |
|---|---|---|
| **1** ✅ | Basic RAG + streaming + citations | [poc/app/rag/](poc/app/rag/), [poc/app/agents/rag_agent.py](poc/app/agents/rag_agent.py) |
| **2** ✅ | LangGraph supervisor + validator with retry loop | [poc/app/graph/](poc/app/graph/), [poc/app/agents/validator_agent.py](poc/app/agents/validator_agent.py) |
| **3** ✅ | Reporting autonomy (Markdown + embedded charts) | [poc/app/reporting/](poc/app/reporting/), [poc/app/agents/report_agent.py](poc/app/agents/report_agent.py) |
| **4** ✅ | SQLite long-term memory + per-user conversations | [poc/app/memory/](poc/app/memory/), [poc/app/agents/memory_agent.py](poc/app/agents/memory_agent.py) |
| **5** ✅ | OpenTelemetry traces + logs + metrics (Aspire Dashboard) | [poc/app/observability/](poc/app/observability/), [poc/scripts/run_observability.sh](poc/scripts/run_observability.sh) |
| **6** ✅ | Per-document ingestion pipeline: PDF → Markdown → metadata sidecar → ChromaDB. Same flow used by the batch script and the `POST /ingest` endpoint for UI uploads | [poc/app/ingestion/](poc/app/ingestion/), [poc/data/knowledge_base/](poc/data/knowledge_base/) |
| **7** 🟡 planned | Year-aware retrieval (KB covers 2020/2021/2022/2024 — 2023 gap), today-aware reasoning, out-of-year fallback, clarifier node, audit-trail SQLite DB | (new) `poc/app/graph/clarifier.py`, `poc/app/audit/`, retriever `where_filter`. Details: [Phase 7](#phase-7--year-aware-rag-clarifier-audit-trail-) |
| **8** 🟡 planned | Talk-to-Data agent over `insurance_kpis.csv` (year / period / channel / product line × 13 KPIs) — natural-language quantitative analysis with drill-down follow-ups and verifiable Operation JSON | (new) `poc/app/agents/data_agent.py`, `poc/app/data/`. Details: [Phase 8](#phase-8--talk-to-data-agent-) |
| **9** 🟡 planned | Executive annual report for a selected year — narrative + KPI highlights + variance commentary + risk indicators + recommendations. Outputs: on-screen Markdown, downloadable DOCX, downloadable PDF | (extends) [poc/app/reporting/](poc/app/reporting/), new `poc/app/reporting/executive/` + `writers/`. Details: [Phase 9](#phase-9--executive-annual-report-) |
| **10** 🟡 planned | PoC stakeholder deck (PPTX + PDF) — non-technical problem framing, retrospective, "what I'd do differently" (AG-UI, Azurized models, one-shot report experiment) | (new) `poc/scripts/build_pptx.py`, `docs/presentation/`. Details: [Phase 10](#phase-10--poc-presentation-deck-) |

### Nice-to-have (not on the roadmap)

Lower-priority items that improve quality but aren't gating the PoC:

- **Table extraction from PDFs** — `pymupdf4llm` handles simple tables but complex multi-page tables sometimes render messily. Falling back to `tabula-py` or `unstructured.io` only for table-heavy docs would yield cleaner chunks for KPI-style retrieval.
- **Unit test coverage** — `tests/unit/test_imports.py` catches gross breakage. Adding focused unit tests for the pure functions (`_clean_section_title`, `_smart_join_pages`, `_parse_validation`, `chunk_metadata`) would lock the chunking + parsing logic against regressions.

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

### Phase 6 — Per-document ingestion pipeline
PDF → Markdown (via `pymupdf4llm`, layout-preserving) → metadata sidecar (validated against [poc/data/knowledge_base/metadata/schema.json](poc/data/knowledge_base/metadata/schema.json)) → ChromaDB with rich chunk metadata. Single entry point `ingest_document(pdf_path, extra_metadata)` powers three callers: the batch script `python scripts/ingest_pdfs.py`, the smoke test, and the **`POST /ingest`** endpoint that accepts file uploads from the (upcoming) UI form. Each ingested chunk carries `title`, `year`, `keywords`, `language`, `document_category`, `source`, `page`, etc. — filterable in Aspire and queryable in the retriever.

**Chunking strategy.** One Markdown file per PDF (with `<!-- page N -->` boundary markers). `RecursiveCharacterTextSplitter` runs on the **whole** body so clauses that straddle pages stay together; per-chunk metadata records the chunk's starting page (and a `pages` list when it spans more than one).

#### Why `chunk_size=1200`, `chunk_overlap=200`

| Setting | Value | Why |
|---|---|---|
| `chunk_size` | **1200** chars | A typical "Section X — …" block from an insurance policy (a clause + its surrounding context) fits comfortably. Small enough that retrieval stays precise — chunks don't drown the embedding in unrelated text. |
| `chunk_overlap` | **200** chars (≈17 %) | Standard 15–20 % overlap. A sentence ending near a chunk boundary is re-presented in the next chunk's prefix, so retrieval still wins on it. |

Tuning knobs (single env var change in `poc/.env`):

| Profile | size / overlap | When |
|---|---|---|
| Conservative | 800 / 120 | Smaller LLM context window, or you want stricter chunk-to-citation precision. More chunks total → slower retrieval. |
| **Recommended** | **1200 / 200** | Default. Tuned for insurance/legal/policy PDFs. |
| Aggressive | 1800 / 300 | Long-form regulations or reports where you want broad context per hit. Risk: noisier retrieval. |

Symptoms → action:
- "Answers miss details I know are in the doc" → chunks may be too small; bump to 1500 / 250.
- "Answers wander, include unrelated facts" → chunks may be too large; drop to 900 / 150.
- After changing, always **reset + re-ingest**: `python scripts/reset_stores.py && python scripts/ingest_pdfs.py`.

What's instrumented:
- **Auto-instrumentation** of FastAPI and httpx — a request from Streamlit → API → graph nodes shows up as a single connected trace.
- **OpenInference LangChain instrumentor** — every LLM / embedding / retriever call gets a span with prompt + completion previews, model name, token usage. Langfuse-style detail in Aspire's Traces tab.
- **Manual spans** on each graph node — `supervisor.classify`, `rag.node`, `rag.reformulate`, `rag.llm.invoke`, `rag.retrieve`, `validator.judge`, `report.node`, `report.extract`, `decline.canned` — with attributes (`user.id`, `conversation.id`, `supervisor.route`, `rag.retry_count`, `validator.grounded`, etc.).
- **OTLP logs** — Python `logging` records flow to Aspire alongside the existing stderr handler, with `trace_id`/`span_id` enrichment.
- **OTLP metrics** — `rag_poc.node.invocations`, `rag_poc.node.duration` (histogram per node), `rag_poc.validator.outcomes{result=pass\|fail}`, `rag_poc.rag.chunks_retrieved`.

Backend: **Aspire Dashboard** as a single Docker container from `mcr.microsoft.com/dotnet/aspire-dashboard:9.0`. OTLP gRPC on `localhost:4317`, web UI on `http://localhost:18888`. Start it with `bash poc/scripts/run_observability.sh` (or just `run_all.sh`). `run_all.sh` recycles the container on every invocation so each run starts with empty telemetry.

### Phase 7 — Year-aware RAG, Clarifier, Audit trail 🟡

Folds three closely-related concerns into the existing graph: temporal awareness, year-scoped retrieval, and an auditable record of every decision.

**Functional bullets**
- **Today-aware reasoning.** `datetime.now()` is injected into `GraphState.today` at graph entry and surfaced in every system prompt so the LLM can resolve relative dates ("10 days ago" → `2026-05-22`).
- **Year-scoped retrieval.** The retriever accepts a `where_filter` forwarded to `Chroma.similarity_search(filter={"year": 2020})`. Year is extracted by a cheap regex (`\b(20\d\d)\b`) on the question, with the supervisor LLM as fallback.
- **Out-of-year fallback.** KB covers **2020 / 2021 / 2022 / 2024** — the **2023 gap** is explicit. When the requested year is outside the covered set the agent declines without retrieving and offers the nearest covered years ("I have 2022 and 2024 — which one applies?").
- **Clarifier node `clarifier.ask`.** Fourth supervisor route `needs_clarification`. Triggers: no year mentioned and history doesn't resolve one · the relevant clause differs materially across years · the year is outside the covered set. Emits one targeted question and ends the turn; the next user message re-enters the supervisor.
- **Worked example (the user's question).** *"A customer requests a refund for a product purchased 10 days ago, no receipt but shows a bank transaction. Based on the 2020 policy, what should I do?"* → supervisor extracts `target_year=2020`, `purchase_date=2026-05-22` → retriever runs with `{"year": 2020}` → validator checks no other-year content leaked in.
- **Audit trail.** New SQLite database `audit.sqlite` (separate file from `memory.sqlite` so business memory and audit telemetry don't share a transaction boundary). Schema:
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
- **Files (new / changed).** `poc/app/graph/clarifier.py` (new) · `poc/app/graph/state.py` (+`today`, `target_year`, `clarifier_reason`) · `poc/app/graph/supervisor.py` (new routes) · `poc/app/llm/prompts/supervisor.txt` (inject `today` + covered-years list) · `poc/app/rag/retriever.py` (accept `where_filter`) · `poc/app/audit/` (new package: `store.py`, `events.py`, `middleware.py`) · `poc/scripts/audit_export.py` (new — CSV dump for compliance review).
- **Out of scope.** UI for the audit log (CSV export is enough for the PoC) · cross-year reformulation (Phase 8/9 concern) · backfilling audit rows for already-stored conversations.

### Phase 8 — Talk-to-Data agent 🟡

Adds a fourth worker agent that answers quantitative questions over a structured KPI dataset, with drill-down follow-ups and verifiable answers.

**Functional bullets**
- **Dataset.** `poc/data/knowledge_base/structured/insurance_kpis.csv` (or `.xlsx`). One row per `(year, period, channel, product_line)`. Same year coverage as the PDFs: **2020 / 2021 / 2022 / 2024**.
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
- **Files (new / changed).** `poc/app/agents/data_agent.py` (new — planner + executor + renderer) · `poc/app/data/loader.py` (new — CSV/XLSX → typed DataFrame) · `poc/app/data/operations.py` (new — `Operation` pydantic schema) · `poc/app/data/executor.py` (new — pandas executor with guards) · `poc/app/llm/prompts/data_planner.txt` (new) · `poc/app/graph/builder.py` (wire `data` route as a terminal node, like report) · `poc/app/graph/state.py` (+`last_data_operation`, `data_table_markdown`) · `poc/app/ui/streamlit_app.py` (render narrative + table + Operation expander) · `poc/data/knowledge_base/structured/insurance_kpis.{csv,schema.json}` (new — seed data).
- **Audit coupling (with Phase 7).** Every data turn writes a `data.execute` event carrying the final `Operation`, the row count returned, and a hash of the underlying CSV at execution time — so the same answer is reproducible weeks later.
- **Out of scope.** Joining the KPI dataset against the policy PDFs (cross-source RAG + data is a Phase 9 concern) · forecasting (TimeGEN-1 is in the strategic roadmap, not this phase) · user-uploaded CSVs.

### Phase 9 — Executive Annual Report 🟡

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
- **Files (new / changed).** `poc/app/reporting/executive/builder.py` (new — orchestrates plan → collect → narrate → assemble) · `poc/app/reporting/executive/sections.py` (per-section dataclasses) · `poc/app/reporting/executive/thresholds.py` (deterministic risk flags) · `poc/app/reporting/writers/{markdown,docx,pdf}_writer.py` (new) · `poc/app/agents/report_agent.py` (extended — dispatch to executive builder when `target_year` is present) · `poc/app/api/routes/reports.py` (new — `GET /reports/{year}.{docx,pdf}`) · `poc/app/llm/prompts/executive/` (new — one prompt template per section).
- **One-shot experiment (called out under Phase 10 retrospective).** Keep the section pipeline as the production path; build a one-call experimental mode behind a feature flag and compare quality on the same year. The user wants this explicitly piloted.
- **Out of scope.** Multi-year reports (one report = one year for v1) · review-and-revise loop · live data refresh (the report is a point-in-time artefact).

### Phase 10 — PoC Presentation deck 🟡

Final stakeholder deliverable. A short, opinionated deck (PDF + PPTX) that explains the PoC to a non-technical reader, captures what made the work interesting, and is honest about what should be done differently next time. Hand-curated content — not auto-generated like the Phase 9 report.

**Functional bullets**
- **Two formats, one source.** Source of truth = `docs/presentation/deck.md` (Markdown). PPTX built via `poc/scripts/build_pptx.py` (`python-pptx`); PDF via `soffice --headless --convert-to pdf` from the PPTX. Both artefacts land in `docs/presentation/insurance-rag-poc.{pptx,pdf}`.
- **Slide A — Problem explanation (non-technical).** For a manager or client with no engineering background.
    > *Insurance branch employees spend an outsized share of their day looking up policy clauses across years of PDFs to answer questions they receive at the counter — "is this refundable?", "is this covered?", "what does the 2020 policy say about this?". The lookups are slow, inconsistent across employees, and impossible to audit after the fact. This PoC shows an assistant that answers those questions in seconds, points to the exact paragraph in the exact PDF it used, and keeps a record of every decision so compliance can review it later. It runs entirely on a workstation — no document or customer detail leaves the building.*
    - Visual: one annotated screenshot of a chat turn with a citation popover open.
- **Slide B — What interested you?** Author's voice. Things that were genuinely fun to build.
    - **Full open solution.** Self-imposed constraint: zero paid LLM APIs. Every design choice ran through the "does this still work on a 7B local model?" filter — which is why it ended up so well-grounded.
    - **Diagram design.** [GRAPH.md](GRAPH.md) and the per-phase architecture sketches. Drawing the state machine before writing the code shaped what actually got built.
    - **The "View chunk" button + Download PDF.** Compliance plumbing disguised as UX — the reviewer can verify any answer by opening the chunk popover or the source PDF in two clicks.
    - **Per-document ingestion → Aspire telemetry.** Chunker / vectorstore spans land in Aspire with attributes that make chunking choices visible (sections, chunks_kept vs skipped). Crucial debugging surface — in past projects we used to back up the index nightly into Postgres just to be able to diff embeddings and verify correct indexing; here the diff lives in telemetry.
    - **A real business-output report from a 7B parameter model.** The Markdown + base64 chart format is a deliberate squeeze of a small local model into a serious deliverable shape.
- **Slide C — What you'd do differently.** Frank assessment. Two–three lines per bullet.
    - **Prioritise Talk-to-Data earlier, but guard it with UI affordances.** Quantitative answers are the highest-value thing the assistant could do for an insurance ops team, and also the easiest to get wrong. A confidently wrong percentage is worse than no agent at all. Cure: surface the underlying rows and the planner `Operation` alongside every numeric answer (this is the Phase 8 design) and add UI helpers — quick-pick dimension chips, a metric glossary — so the user is steered into well-formed questions rather than free-typing pitfalls.
    - **Use AG-UI as the front-end protocol.** Streamlit was the right call for a PoC; rebuilding on AG-UI would give us streaming tool calls, native human-in-the-loop, and a real component model instead of `st.rerun()`.
    - **Azurize the model layer.** Drop Ollama 7B for production: **GPT-5.1** as the RAG generator (substantial grounded-answer quality lift over local 7B) · **mini / nano model** for the query reformulator (sub-second latency, cheap, small task) · **GPT-5.4 / reasoning-medium** for the executive report (multi-section pipeline benefits disproportionately from a reasoning model).
    - **End-to-end report generation in a single LLM call** as a side-by-side experiment against the per-section pipeline. The challenge is getting a stable executive-grade structure out of one shot; the prize is dramatically lower latency and cost. Worth one focused spike before committing to the orchestrated pipeline as the long-term path.
- **Out of scope.** Animated transitions / video walk-through · speaker-notes export (notes live as block-comments in the source Markdown but no separate render) · CI rebuild on every commit (single make target is enough).

---

## 🔒 Privacy Guarantee

All inference, embeddings, vector storage, and memory persistence happen on the local workstation. **No PII or policy document content is ever transmitted to a third-party LLM API.** OpenTelemetry data (span attributes, structured logs, metrics) stays inside the local Aspire container. This architecture is designed for GDPR and EU AI Act alignment from day one.
