# Phase Backlog & Prioritisation Prep

> Living document — updated after each phase. Sources: `README.md` roadmap,
> `ideas.txt`, `docs/insurance_rag_strategic_roadmap.md`, and the Phase 13b
> post-implementation review.

---

## Immediate fixes (not phases — ship on the current branch or next hotfix)

| # | Item | Source | Effort |
|---|------|---------|--------|
| F1 | **STT model pre-download at setup** — On macOS, faster-whisper downloads the Whisper model from HuggingFace on the *first transcription call*, which hits HF's unauthenticated rate limit. The model download must move into `setup_macos.sh` (and `setup_wsl.sh`) alongside the Piper model step. | `ideas.txt` | S |
| F2 | **HuggingFace token in setup** — Add `HF_TOKEN` as an optional env var in `.env.example` and pass it during setup so authenticated downloads avoid rate limits and work in CI. | `ideas.txt` | S |
| F3 | **Update `insurance_rag_strategic_roadmap.md` Phase 13 entry** — Row currently reads `Planned`; should be `✅`. | Internal | XS |

---

## Phase 14 — Cross-conversation planning 📋

**Goal:** Lift Plans from per-turn artefacts to first-class memory objects that persist across
sessions, days, and users.

**Key capabilities:**
- Plan persistence beyond a turn — users can pick up `"the 2024 annual report you were
  generating last Tuesday"` via a resume-token chip in the UI or `/resume <plan_id>` in chat.
- Plan-aware episodic memory — the Phase 4 rolling-summarisation includes the current plan
  state so the assistant doesn't lose context across sessions.
- Multi-user plans — a Step can require approval from a different `user_id` than the initiator;
  ACLs enforced at the Orchestrator.
- Plan migration hooks — when a Skill's `input_schema` evolves, persisted Plans get a
  `migrate_v{n}_to_v{n+1}` hook at resume time.
- UI sidebar panel — *"Your plans"* list (pending · in-progress · done · expired) with
  one-click resume.

**Out of scope:** Plan branching/forking · cross-tenant plans · plan-of-plans.

**Dependencies:** Phase 12 `plans` table already exists; the schema needs a `ttl=NULL` variant
and a `participants` column.

---

## Phase 15 — Recursive Skill composition 📋

**Goal:** Let a Skill emit a sub-Plan mid-execution. The Orchestrator becomes recursive.

**Key capabilities:**
- A Worker can return `SubPlanRequest{steps, merge_strategy}` instead of a `StepResult`.
- Recursion budgets: `max_recursion_depth` (default 3), shared `max_steps` /
  `max_tool_calls` / `max_seconds` across parent + children.
- Cycle detection — a Step that re-emits its own `skill_name` is rejected.
- OTel renders the nested span tree; audit replay handles recursion transparently.

**Use case:** *"Generate annual report → each section Skill spawns a data-quality-check
sub-Plan → merge → return the umbrella summary."*

**Out of scope:** Skills loaded from external sources · cross-thread sub-Plan parallelism ·
sub-Plans that mutate the parent's `args`.

---

## Phase 16 (proposed) — Language-aware pipeline & multilingual answers

**Goal:** Detect the question language and reply in the same language. Currently the
LangGraph pipeline is English-only; Phase 13 added Greek *voice* but the LLM answers
are always in English.

**Two implementation strategies (trade-offs below):**

### Option A — Translate the LLM reply
- Detect question language (LangDetect / Whisper `info.language` already returned from STT).
- After Assembler produces an English answer, call a lightweight translation step
  (local MarianMT or Ollama with a multilingual model) before streaming to the client.
- **Pro:** Source documents unchanged; single retrieval index.
- **Con:** Translation latency (~0.5–2 s); translation errors compound on top of LLM errors;
  citations remain in English.

### Option B — Translate the source documents and re-index
- Run the existing ingestion pipeline on Greek-translated versions of the PDFs.
- Store both EN and EL variants in ChromaDB with a `language` metadata field.
- Retriever filters by detected question language.
- **Pro:** Full end-to-end Greek — citations also in Greek; no translation latency at query time.
- **Con:** Ingestion overhead (~60 s per PDF for translation); storage doubles; translation
  quality of legal/insurance text needs validation.

**Recommended starting point:** Option A (reply translation) — lower risk, reversible,
lets the team validate Greek answer quality before committing to Option B.

**What Phase 13 already provides:** `info.language` from STT, language passed to TTS, EN/ΕΛ
toggle in the UI. Phase 16 only needs to wire translation into the Assembler output path.

**Effort estimate:** M (Option A) / L (Option B).

---

## Phase 17 (proposed) — Enterprise governance layer

From `ideas.txt` — enterprise-readiness features needed before a production handoff.

| Capability | Description | Effort |
|---|---|---|
| **Prompt registry** | Version-controlled store of all system prompts + skill prompts with SHA256 fingerprints. Audit row links every LLM call to the prompt version used. Enables A/B testing and rollback without a code deploy. | M |
| **Skills registry** | Formal versioned registry (extending the current auto-discovery) with `schema_version`, deprecation flags, and a `/admin/skills` endpoint. Lays the ground for Phase 15's migration hooks. | S |
| **Auto-evaluation pipeline** | Scheduled eval runs comparing LLM answers against a golden set. WER (Phase 13b) is the first metric; extend to RAGAS (faithfulness, answer relevance, context recall), latency p95, and validator pass-rate. | M |
| **MCP Gateway** | Expose Skills and Tools as MCP tools behind a standard gateway so external agents (Claude Desktop, Cursor, etc.) can invoke them. Maps cleanly onto the existing `AgentTool` + `Skill` structure. | M |
| **OAuth 2.0 / SSO** | Replace the current `user_id` string with a proper identity token. OIDC-compatible; integrates with Azure Entra ID for enterprise SSO. Prerequisite for document-level RBAC. | L |
| **Document-level RBAC** | ChromaDB metadata `user_group` field already planned in the strategic schema (§ 2.2.2). Retriever filters by `user_group` from the OAuth token. | M |

**Recommended order:** Skills registry → Prompt registry → Auto-eval → MCP Gateway →
OAuth 2.0 → RBAC. OAuth / RBAC depend on each other; the rest are independent.

---

## Tech debt / nice-to-have (no phase assigned)

| Item | Why deferred | Effort |
|---|---|---|
| **Table extraction from PDFs** — fall back to `tabula-py` / `unstructured.io` for complex multi-page tables that `pymupdf4llm` renders messily | Low frequency in current KB; revisit when more structured data PDFs are ingested | S |
| **Unit test coverage** — focused tests for pure functions (`_clean_section_title`, `_smart_join_pages`, `_parse_validation`, `chunk_metadata`) | Current `test_imports.py` catches gross breakage; full coverage would lock chunking logic | M |
| **STT streaming** — begin building the Planner's Plan while transcription is still in progress | Complex; requires WebSocket or chunked response; deferred until voice usage grows | L |
| **Voice cloning** | Out of scope for PoC; would require a heavier TTS model and explicit user consent | XL |
| **Image / vision inputs** | No phase yet; would require a multi-modal LLM (e.g. `llava` via Ollama) | L |
| **Real-time bidirectional voice** | Full-duplex audio; architectural change; out of PoC scope | XL |

---

## Strategic roadmap coverage gaps

Cross-referencing `docs/insurance_rag_strategic_roadmap.md` §5 against the PoC phases.

| Strategic component | PoC phase | Gap? |
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
| Cross-conversation planning | Phase 14 | 📋 planned |
| Recursive Skill composition | Phase 15 | 📋 planned |
| Multilingual pipeline (EN/EL) | Phase 16 (proposed) | ❌ gap |
| Prompt registry | Phase 17 (proposed) | ❌ gap |
| MCP Gateway | Phase 17 (proposed) | ❌ gap |
| OAuth 2.0 / SSO | Phase 17 (proposed) | ❌ gap |
| Document-level RBAC | Phase 17 (proposed) | ❌ gap |
| Auto-evaluation pipeline | Phase 17 (proposed) | ❌ gap |
| Azure Document Intelligence (scanned PDFs) | Not planned | ❌ gap (cloud dependency) |
| SharePoint connectors | Not planned | ❌ gap (cloud dependency) |
| Multi-tenant architecture | Not planned | ❌ gap (architecture change) |
| TimeGEN-1 forecasting | Not planned | ❌ gap (separate model) |

---

## Suggested prioritisation order

```
NOW (hotfix)
  F1 STT pre-download at setup
  F2 HF_TOKEN in setup
  F3 Update strategic roadmap doc

NEXT (Phase 14)
  Cross-conversation planning
  → already partially built (plans table exists from Phase 12)
  → highest user-visible value ("resume my report from yesterday")

THEN (Phase 15)
  Recursive Skill composition
  → enables complex multi-step autonomous workflows
  → depends on Phase 14 plan persistence

PARALLEL TRACK — Language (Phase 16)
  Multilingual answer pipeline (Option A first)
  → small team can run this while Phase 14/15 are in progress
  → Phase 13 already wired language detection from STT

PARALLEL TRACK — Governance (Phase 17)
  Skills registry → Prompt registry → Auto-eval → MCP Gateway → OAuth → RBAC
  → enterprise handoff readiness; not gating PoC capabilities
```
