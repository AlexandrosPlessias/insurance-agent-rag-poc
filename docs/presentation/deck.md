# ACME Insurances — Local RAG PoC

> Source of truth for the stakeholder deck. `poc/scripts/build_pptx.py`
> reads this file and emits `docs/presentation/insurance-rag-poc.pptx`.
>
> Slide grammar:
>   `## <Title>` starts a new slide.
>   `image: <name>.png` line embeds a screenshot from `docs/screens/`
>     (or renders a "TODO: capture <name>.png" placeholder if absent).
>   `note: <one-line caption>` adds a caption under the image.
>   Anything else inside a slide is bullet/prose body, rendered as
>   slide content via python-pptx's text-frame.

---

## ACME Insurances · Local RAG PoC

ACME Insurances — Assistant for branch operators

A locally-running agentic RAG system that answers policy & KPI questions
in seconds — citing the exact paragraph it used, audit-trail attached.

note: Cover slide. Speaker introduces themselves and the demo.

---

## What this PoC solves

Branch employees lose hours every day looking up policy clauses across
years of PDFs to answer customer questions — "is this refundable?",
"is this covered?", "what did the 2020 contract say?".

- Lookups are slow, inconsistent across employees, hard to audit.
- This PoC answers in seconds, **points to the exact paragraph** it used,
  and **logs every decision** for compliance review.
- Runs **entirely on a workstation** — no document or customer detail
  leaves the building.

image: 10.acme-brand-header.png
note: Branded UI — ACME shield, conversation list, citation popovers.

---

## The seven-route state machine

The supervisor classifies every question into exactly one route. Each
route has its own contract; severity decisions are deterministic, not
LLM-decided.

- **RAG** — policy questions, year-scoped retrieval, validator + retry
- **Report** — policy summary OR Phase 9 executive annual report
- **Data** — quantitative questions over the KPI dataset
- **Clarifier** — asks one targeted question when the year is missing
- **Out-of-year fallback** — refuses 2023 (the KB gap) gracefully
- **Decline** — out-of-scope politely

image: 11.full-topology-stepper.png
note: All 7 nodes on every turn; the active branch lights up green.

---

## Year-aware retrieval & clarifier (Phase 7)

KB covers 2020 / 2021 / 2022 / 2024. The 2023 gap is intentional.

- A bare *"What is the refund window?"* triggers the clarifier — no
  silent year inheritance, no wrong-year answer.
- A *"2024"* reply gets stitched onto the original question.
- *"What does the 2023 policy say?"* short-circuits **before any LLM call**
  to a templated reply naming the nearest covered years.

image: 12.clarifier-turn.png
note: Clarifier fires when the year is missing — the operator picks.

---

## Talk-to-Data agent (Phase 8)

The planner LLM emits a **typed Operation JSON**; a hand-written pandas
executor consumes it. The LLM never writes code.

- 14 metrics across year · period · channel · product line.
- Five schema-aware guards: year_gap · invalid_aggregation ·
  unknown_metric · unknown_dimension_value · empty_result.
- Drill-down via prompt patch-mode — *"now break by product"* inherits
  metric/year/aggregation, changes only group_by.

image: 13.data-turn-with-table.png
note: Narrative + Markdown table + Operation JSON expander.

---

## Drill-down — inherited / changed chips

image: 14.data-drilldown-chips.png
note: The expander labels which Operation fields carried over and which
  the user changed this turn. Compliance reviewers can replay any answer
  by re-running the Operation against the same CSV sha256.

---

## Executive annual report (Phase 9)

Section-by-section pipeline (collector → narrator → assemble) over the
Phase 8 KPI data + Phase 1 policy chunks.

- **Deterministic** risk-flag severity — green/amber/red bands in
  `thresholds.py`, not LLM-decided.
- Three writers: on-screen Markdown, downloadable DOCX, downloadable PDF.
- Reproducibility hash `report_run_id = sha256(year + csv_sha + git_sha)[:12]`
  — same triple, same id.

image: 15.executive-report-rendered.png
note: 2024 report — KPI grid + first trend chart visible.

---

## Risk indicators — deterministic bands

image: 16.executive-risk-badges.png
note: Five indicators with hand-coded green/amber/red thresholds.
  Severity is band-lookup, never LLM-decided — the single point of
  LLM-free trust in the whole report.

---

## DOCX · PDF · MD downloads

image: 17.executive-downloads.png
note: Three download buttons under every executive report, with the
  run-id caption so reviewers can confirm "same id = same numbers".
  The same report id reappears if (year, csv_sha256, git_sha) match.

---

## Observability: every decision in Aspire

image: 18.aspire-trace-detail.png
note: A single chat turn fans out into supervisor → data.plan →
  data.execute → render spans, with prompt/completion previews and token
  counts. Every node also writes an audit row keyed by trace_id.

---

## Audit trail · compliance export

image: 19.audit-export-csv.png
note: `python scripts/audit_export.py` dumps every routing / retrieval /
  validation / clarifier / data.plan / data.execute decision to CSV with
  the trace_id, ready for a compliance reviewer's PowerBI / Splunk.

---

## What interested me

Personal voice from the author — things that were genuinely fun to build.

- **Full open-source constraint.** Zero paid LLM APIs. Every design choice
  ran through the "does this still work on a local 7B model?" filter.
- **Diagram design.** [GRAPH.md](../../GRAPH.md) and the per-phase sketches.
  Drawing the state machine before the code shaped what actually got built.
- **The "View chunk" + Download PDF buttons.** Compliance plumbing
  disguised as UX — any answer is verifiable in two clicks.
- **Aspire telemetry on the chunker / vectorstore.** Sections, chunks_kept
  vs skipped, embedding spans — all visible. In past projects we used to
  back up the index nightly into Postgres just to diff embeddings. Here
  the diff lives in telemetry.
- **A real BO-grade report from a 7B model.** The Markdown + chart +
  Operation expander format is a deliberate squeeze of a small local
  model into a serious deliverable shape.

---

## What I would do differently

Honest retrospective.

- **Prioritise Talk-to-Data earlier, but guard it with UI affordances.**
  Quantitative answers are the highest-value thing the assistant can do
  for an insurance ops team — and the easiest to get wrong. A confidently
  wrong percentage is worse than no agent at all. Cure: surface the
  underlying rows + the planner Operation alongside every numeric answer
  (this is the Phase 8 design); add quick-pick dimension chips + a metric
  glossary in the UI so users are steered into well-formed questions.
- **Use AG-UI as the front-end protocol.** Streamlit was the right call
  for a PoC; rebuilding on AG-UI would give streaming tool calls, native
  human-in-the-loop, and a real component model instead of `st.rerun()`.
- **Azurize the model layer for production.** Drop Ollama 7B:
  GPT-5.1 for the RAG generator (substantial grounded-answer quality lift),
  a mini / nano model for the query reformulator (sub-second, cheap),
  GPT-5.4 / reasoning-medium for the executive report (the multi-section
  pipeline benefits disproportionately from a reasoning model).
- **End-to-end report generation in a single LLM call** as a side-by-side
  experiment against the per-section pipeline. The challenge is stable
  executive-grade structure out of one shot; the prize is dramatically
  lower latency and cost. Worth one focused spike before committing.

---

## Thank you

Questions, demo requests, code review — happy to dive in.

note: Closing slide. Speaker invites questions.
