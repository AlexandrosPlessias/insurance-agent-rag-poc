# Phase Backlog & Prioritisation

> Living document — updated after each phase.

---

## Immediate fixes

| # | Item | Effort |
|---|------|--------|
| ~~F1~~ | ~~**STT model pre-download at setup**~~ — ✅ Done | — |
| F2 | **HuggingFace token in setup** — Optional: add `HF_TOKEN` to `.env.example` for authenticated model downloads. The setup step already has a soft WARN fallback so it never blocks first run. | S |
| ~~F3~~ | ~~**Update strategic roadmap Phase 13 entry**~~ — ✅ Done | — |

---

## Phase 15 — Cross-conversation planning 📋

**Goal:** Lift Plans from per-turn artefacts to first-class memory objects that persist across sessions, days, and users.

**Key capabilities:**
- Plan persistence beyond a turn — users can pick up *"the 2024 annual report you were generating last Tuesday"* via a resume-token chip in the UI or `/resume <plan_id>` in chat.
- Plan-aware episodic memory — rolling-summarisation includes the current plan state so the assistant doesn't lose context across sessions.
- Multi-user plans — a Step can require approval from a different `user_id` than the initiator; ACLs enforced at the Orchestrator.
- Plan migration hooks — when a Skill's `input_schema` evolves, persisted Plans get a `migrate_v{n}_to_v{n+1}` hook at resume time.
- UI sidebar panel — *"Your plans"* list (pending · in-progress · done · expired) with one-click resume.

**Out of scope:** Plan branching/forking · cross-tenant plans · plan-of-plans.

**Dependencies:** Phase 12 `plans` table already exists; the schema needs a `ttl=NULL` variant and a `participants` column.

---

## Phase 16 — Recursive Skill composition 📋

**Goal:** Let a Skill emit a sub-Plan mid-execution. The Orchestrator becomes recursive.

**Key capabilities:**
- A Worker can return `SubPlanRequest{steps, merge_strategy}` instead of a `StepResult`.
- Recursion budgets: `max_recursion_depth` (default 3), shared `max_steps` / `max_tool_calls` / `max_seconds` across parent + children.
- Cycle detection — a Step that re-emits its own `skill_name` is rejected.
- OTel renders the nested span tree; audit replay handles recursion transparently.

**Use case:** *"Generate annual report → each section Skill spawns a data-quality-check sub-Plan → merge → return the umbrella summary."*

**Out of scope:** Skills loaded from external sources · cross-thread sub-Plan parallelism · sub-Plans that mutate the parent's `args`.

---

## Phase 17 — Full Greek Support 🇬🇷 📋

**Goal:** End-to-end Greek experience — Greek documents, Greek answers, Greek UI. Phase 13 added Greek voice (STT + TTS), but the LLM answers, source documents, and UI labels remain English-only. Phase 17 closes all remaining gaps.

### Deliverables

| Area | Deliverable | Notes |
|---|---|---|
| **KB documents** | Greek versions of the insurance PDFs ingested alongside English originals | `language: el` metadata; retriever filters by detected language |
| **Answer language** | Assembler produces answers in Greek when the question is Greek | See Option A / B below |
| **React SPA i18n** | UI labels, placeholders, and button text translated to Greek | `react-i18next`; `en.json` + `el.json` locale files; language toggle in header |
| **Citations** | Citation text rendered in Greek when EL KB variant is used | Depends on Option B |
| **STT / TTS** | Already live from Phase 13 — Whisper EL + Piper EL voice | No new work |

### Answer generation strategies

**Option A — Translate the LLM reply**
- Detect question language (`LangDetect` / Whisper `info.language` already returned from STT).
- After Assembler produces an English answer, call a lightweight translation step (Ollama `qwen2.5:7b` handles Greek) before streaming to the client.
- Pro: source documents unchanged; single retrieval index.
- Con: translation latency (~0.5–2 s); citations remain in English.

**Option B — Translate source documents and re-index**
- Run the existing ingestion pipeline on Greek-translated versions of the PDFs.
- Store both EN and EL variants in ChromaDB with a `language` metadata field.
- Pro: full end-to-end Greek — citations also in Greek; no translation latency at query time.
- Con: ingestion overhead (~60 s per PDF); storage doubles.

**Recommended starting point:** Option A (reply translation) — lower risk, reversible.

**What Phase 13 already provides:** `info.language` from STT, language passed to TTS, EN/EL toggle in the UI. The Assembler output path and the React i18n layer are the only gaps.

**Effort estimate:** M (Option A + i18n) / L (Option B full re-index).

---

## Phase 18 — Enterprise governance layer 📋

| Capability | Description | Effort |
|---|---|---|
| **Prompt registry** | Version-controlled store of all system prompts with SHA256 fingerprints. Audit row links every LLM call to the prompt version used. Enables A/B testing and rollback without a code deploy. | M |
| **Skills registry** | Formal versioned registry (extending the current auto-discovery) with `schema_version`, deprecation flags, and a `/admin/skills` endpoint. | S |
| **Auto-evaluation pipeline** | Scheduled eval runs comparing LLM answers against a golden set. Extends to RAGAS (faithfulness, answer relevance, context recall), latency p95, and validator pass-rate. | M |
| **MCP Gateway** | Expose Skills and Tools as MCP tools so external agents (Claude Desktop, Cursor, etc.) can invoke them. | M |
| **OAuth 2.0 / SSO** | Replace the current `user_id` string with a proper identity token. OIDC-compatible; integrates with Azure Entra ID. Prerequisite for RBAC. | L |
| **Document-level RBAC** | ChromaDB metadata `user_group` field. Retriever filters by `user_group` from the OAuth token. | M |

**Recommended order:** Skills registry → Prompt registry → Auto-eval → MCP Gateway → OAuth 2.0 → RBAC.

---

## Phase 19 — Regression Test Suite & Evaluation Harness 🧪 📋

**Goal:** Automated evaluation harness that runs a golden set of queries through the full pipeline and scores answer quality. Acts as a regression gate — catches model drift, prompt regressions, and retrieval degradation before they reach users.

### Components

| Component | Description |
|---|---|
| **Golden dataset** | `tests/evals/golden_set.yaml` — each entry: question, expected route, expected answer excerpt, expected citation sources, latency ceiling |
| **Eval runner** | `scripts/run_evals.py` — hits the live `/chat` endpoint (not mocked), captures responses, scores each dimension |
| **RAGAS-style metrics** | Faithfulness, answer relevance, context recall, citation precision |
| **LLM-as-judge** | Secondary Ollama call scoring each answer 0–2 against the golden reference; separate model to avoid self-scoring bias |
| **Regression gate** | Non-zero exit if mean score drops below configurable threshold (default 1.5 / 2.0) |
| **Aspire metrics** | Eval scores emitted as OTLP metrics (`rag_poc.eval.score`, `rag_poc.eval.faithfulness`) so trends are visible over time |
| **CI integration** | Optional GitHub Actions step on every PR to `dev`; blocks merge on regression |

### Golden set structure (example)

```yaml
- id: refund_window_2024
  question: "What is the refund window in 2024?"
  expected_route: rag
  expected_citation_sources:
    - Enhanced_Customer_Guidelines_2024.pdf
  answer_must_contain:
    - "30 days"
  latency_ceiling_s: 60

- id: kpi_claims_2022
  question: "What were total claims in 2022?"
  expected_route: data
  answer_must_contain:
    - "2022"
  latency_ceiling_s: 30
```

**Dependencies:** Phase 14 Docker stack (eval runner hits the live gateway endpoint).

**Effort estimate:** M

---

## Tech debt / nice-to-have

| Item | Why deferred | Effort |
|---|---|---|
| **Table extraction from PDFs** — fall back to `tabula-py` / `unstructured.io` for complex multi-page tables that `pymupdf4llm` renders messily | Low frequency in current KB | S |
| **Unit test coverage** — focused tests for pure functions (`_clean_section_title`, `_smart_join_pages`, `_parse_validation`, `chunk_metadata`) | Current `test_imports.py` catches gross breakage | M |
| **STT streaming** — begin building the Planner's Plan while transcription is still in progress | Complex; requires WebSocket; deferred until voice usage grows | L |
| **Voice cloning** | Out of scope for PoC; heavier TTS model + explicit user consent required | XL |
| **Image / vision inputs** | No phase yet; requires a multi-modal LLM (e.g. `llava` via Ollama) | L |
| **Real-time bidirectional voice** | Full-duplex audio; architectural change; out of PoC scope | XL |
| **Kubernetes + Helm** | Docker Compose fully meets PoC needs; K8s adds operational complexity with no benefit at this scale | L |

---

## Strategic roadmap coverage

Cross-referencing `docs/insurance_rag_strategic_roadmap.md` §5 against the PoC phases.

| Strategic component | PoC phase | Status |
|---|---|---|
| PDF ingestion + ChromaDB | Phase 6 | ✅ covered |
| LLM metadata sidecar | Phase 6 | ✅ covered |
| Year-aware RAG + clarifier | Phase 7 | ✅ covered |
| Talk-to-Data (pandas) | Phase 8 | ✅ covered |
| Audit trail + OTel | Phase 5, 7 | ✅ covered |
| Executive report (DOCX/PDF/MD) | Phase 9 | ✅ covered |
| Planner · Orchestrator · Workers · Skills | Phase 11 | ✅ covered |
| Feedback ingestion loop | Phase 11 | ✅ covered |
| HITL approval gates + Telegram | Phase 12 | ✅ covered |
| Multi-modal voice (STT + TTS) | Phase 13 | ✅ covered |
| Container orchestration — Docker Compose | Phase 14 | ✅ covered |
| PostgreSQL (multi-pod DB) | Phase 14 | ✅ covered |
| ChromaDB server mode | Phase 14 | ✅ covered |
| Cross-conversation planning | Phase 15 | 📋 planned |
| Recursive Skill composition | Phase 16 | 📋 planned |
| Full Greek support (EN/EL pipeline + i18n) | Phase 17 | 📋 planned |
| Prompt registry | Phase 18 | 📋 planned |
| MCP Gateway | Phase 18 | 📋 planned |
| OAuth 2.0 / SSO | Phase 18 | 📋 planned |
| Document-level RBAC | Phase 18 | 📋 planned |
| Regression test suite & evaluation harness | Phase 19 | 📋 planned |
| Kubernetes + Helm deployment | Deferred | 📋 nice-to-have |
| Azure Document Intelligence (scanned PDFs) | Not planned | ❌ gap (cloud dependency) |
| SharePoint connectors | Not planned | ❌ gap (cloud dependency) |
| Multi-tenant architecture | Not planned | ❌ gap (architecture change) |
| TimeGEN-1 forecasting | Not planned | ❌ gap (separate model) |

---

## Suggested prioritisation order

```
FEATURE TRACK (sequential — each depends on the previous)
  Phase 15  Cross-conversation planning
            → plans table already exists from Phase 12
            → highest user-visible value: "resume my report from yesterday"

  Phase 16  Recursive Skill composition
            → enables complex multi-step autonomous workflows
            → depends on Phase 15 plan persistence

LANGUAGE TRACK (parallel — independent)
  Phase 17  Full Greek support
            → Option A (translate LLM reply) first — low risk, reversible
            → Phase 13 STT already returns info.language
            → also covers React SPA i18n

QUALITY TRACK (parallel — independent)
  Phase 19  Regression test suite & evaluation harness
            → golden_set.yaml + run_evals.py hitting live gateway
            → RAGAS-style metrics + LLM-as-judge + Aspire metric export

GOVERNANCE TRACK (parallel — enterprise readiness)
  Phase 18  Skills registry → Prompt registry → Auto-eval
            → MCP Gateway → OAuth 2.0 → RBAC
            → not gating PoC capabilities; targets production handoff

DEPENDENCY GRAPH
  15 → 16
  17 ──── independent
  18 ──── independent (OAuth blocks RBAC internally)
  19 ──── independent
```
