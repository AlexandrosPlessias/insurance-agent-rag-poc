# ACME Insurances — Local RAG PoC

> Source of truth for the stakeholder deck. `src/scripts/build_pptx.py`
> reads this file and emits `docs/presentation/insurance-rag-poc.pptx`.
>
> Slide grammar:
>   `## <Title>`              starts a new slide.
>   `image: <name>.png`       embeds a screenshot from `docs/screens/`
>                             (or renders a "TODO: capture …" placeholder).
>   `note: <line>`            speaker note (PPTX notes pane, not on the
>                             slide itself — invisible to the audience).
>   Anything else inside a slide is slide body (bullets + prose).

---

## ACME Insurances · Local RAG PoC

A locally-running agentic assistant for branch operators

- Answers policy & KPI questions in seconds
- Cites the exact paragraph it used
- Logs every decision for compliance review
- Runs 100% on the workstation — nothing leaves the building

note: Cover slide. Speaker introduces themselves and the demo.

---

## What this PoC solves

- Branch employees spend hours every day looking up policy clauses
- Lookups are slow, inconsistent, and impossible to audit after the fact
- This assistant answers in seconds with citations + audit trail
- Local-only — no PII or document content ever leaves the workstation

image: 10.acme-brand-header.png

---

## Seven-route state machine

Every question routes to exactly one of seven branches

- **RAG** — policy questions, year-scoped retrieval, validator + 1 retry
- **Report** — single-policy summary OR executive annual report
- **Data** — quantitative questions over the KPI dataset
- **Clarifier** — one targeted question when the year is missing
- **Out-of-year fallback** — graceful refusal for the 2023 gap
- **Decline** — out-of-scope handled politely

image: 11.full-topology-stepper.png

---

## LangGraph — compiled state machine

The seven-route topology as the actual compiled graph

- Source of truth: [`src/agentic_backend/graph/builder.py`](../../src/agentic_backend/graph/builder.py)
- Per-node contracts (MUST / MUST-NOT): [`docs/agent_topology.md`](../agent_topology.md)
- Colour code: 🟦 router · 🟩 worker · 🟧 guard · ⬛ terminal
- Every node carries an OTel span; every edge is auditable

image: 20.langgraph-topology.png

---

## Year-aware retrieval & clarifier

Knowledge base covers 2020 · 2021 · 2022 · 2024 — the 2023 gap is intentional

- *"What's the refund window?"* → clarifier asks the year (no silent guess)
- *"2024"* reply → stitched onto the original question, routed to RAG
- *"What does the 2023 policy say?"* → refused **before any LLM call**

image: 12.clarifier-turn.png

---

## Talk-to-Data agent

Quantitative answers over 14 KPIs — without letting the LLM touch pandas

- Planner LLM emits a **typed Operation JSON**
- A hand-written pandas executor consumes it
- Five schema-aware guards (no `sum` on rates, no 2023, …)
- Drill-down via prompt patch-mode (*"now break by product"*)

image: 13.data-turn-with-table.png

---

## Drill-down — inherited / changed

Every follow-up shows what carried over and what changed

- **Inherited:** metric · filters · aggregation
- **Changed:** group_by
- Compliance reviewers can replay any answer by re-running the
  Operation against the same `csv_sha256`

image: 14.data-drilldown-chips.png

---

## Executive annual report

Section-by-section pipeline · three delivery formats

- Collector → Narrator → Assemble → Writers
- Per-section LLM grounding — the model is bounded to ONE section
  at a time and only sees that section's structured inputs
- Three writers from one source: Markdown · DOCX · PDF
- `report_run_id = sha256(year + csv_sha + git_sha)[:12]` in the footer

image: 15.executive-report-rendered.png

---

## Risk indicators — deterministic bands

Severity is band lookup, never LLM-decided

- 🟢 Loss ratio  ·  🟡 Settlement drift  ·  🔴 Compliance incidents
- All five thresholds hand-coded in `thresholds.py`
- Single point of LLM-free trust in the whole report

image: 16.executive-risk-badges.png

---

## DOCX · PDF · MD downloads

Three buttons under every executive report

- Same `ReportDocument` rendered to all three formats
- API endpoint `GET /reports/{year}.{md|docx|pdf}` for direct downloads
- Run-id caption: *"same id = same numbers"*

image: 17.executive-downloads.png

---

## Observability — every decision in Aspire

OpenTelemetry traces, logs, and metrics out of the box

- One trace per chat turn — supervisor → worker → validator
- LangChain calls auto-instrumented (prompts, completions, tokens)
- Custom spans per node + per sub-step (reformulate / retrieve / answer)

image: 18.aspire-trace-detail.png

---

## Audit trail — compliance export

Every routing / retrieval / validation / data / report decision recorded

- `data/audit.sqlite` — separate from conversation memory
- Each row carries the OTel `trace_id` for cross-reference
- `python scripts/audit_export.py` → CSV ready for PowerBI / Splunk
- *"Why did the model reason this way?"* — answerable weeks later

image: 19.audit-export-csv.png

---

## What I enjoyed building

- **Full open-source constraint.** Zero paid LLM APIs. Every design
  ran through the "does this still work on a local 7B model?" filter
- **Diagram-first design.** Drawing the state machine before the code
  shaped what got built
- **"View chunk" + Download PDF.** Compliance plumbing disguised as UX
- **Chunker telemetry in Aspire.** Sections, chunks kept vs skipped,
  embedding spans — all visible without a separate dashboard
- **A real BO-grade report from a 7B model.** Markdown + chart +
  Operation expander — a deliberate squeeze of a small local model
  into a serious deliverable shape
- **Three-format executive report from one source.** Same typed
  `ReportDocument` → Markdown / DOCX / PDF. Per-section LLM
  grounding + deterministic risk bands + reproducibility hash

---

## What I would do differently

- **Prioritise Talk-to-Data earlier — but guard it with UI affordances.**
  Quantitative answers are the highest-value thing the assistant can
  do, and the easiest to get wrong. Surface rows + Operation alongside
  every numeric answer; add quick-pick dimension chips + a metric
  glossary so users are steered into well-formed questions
- **Use AG-UI as the front-end protocol.** Streamlit was the right call
  for a PoC; AG-UI brings streaming tool calls, native human-in-the-loop,
  and a real component model
- **Azurize the model layer for production.** GPT-5.1 for RAG · mini/nano
  for query reformulation · GPT-5.4 / reasoning-medium for the executive
  report (multi-section pipelines benefit disproportionately from a
  reasoning model)
- **One-shot executive report** as a side-by-side experiment against
  the per-section pipeline. The challenge is structural stability; the
  prize is dramatically lower latency and cost

---

## Northstar — production architecture on Azure

Where this PoC graduates to with Azurized models + cloud infra

- **RAG generator** — GPT-5.1 for grounded answers
- **Query reformulator** — mini / nano model for sub-second latency
- **Executive report narrator** — GPT-5.4 / reasoning-medium (multi-section
  pipelines benefit disproportionately from a reasoning model)
- **Vector store** — Azure AI Search with hybrid retrieval
- **Telemetry** — Azure Monitor + **Langfuse** for LLM-specific signals
- **Compliance** — EU AI Act record-keeping via immutable Blob Storage

image: 21.azure-northstar.png

---

## Thank you

Questions, demo requests, code review — happy to dive in.

note: Closing slide. Speaker invites questions.
