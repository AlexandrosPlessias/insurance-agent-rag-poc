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

## Phase 18 (proposed) — Container orchestration & microservices

**Goal:** Break the monolithic FastAPI backend into isolated, independently deployable
service pods. Introduce a management platform for viewing, updating, and monitoring the
running stack — replacing the current "run everything in one process" model.

---

### Service decomposition

```
┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│   frontend   │   │  api-gateway │   │ voice-service│
│  Nginx + SPA │   │  FastAPI     │   │ STT + TTS    │
│  :5173/80    │   │  :8000       │   │  :8001       │
└──────────────┘   └──────┬───────┘   └──────────────┘
                          │ routes to
          ┌───────────────┼────────────────┐
          ▼               ▼                ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│  agentic-svc │  │  rag-service │  │ingestion-svc │
│  LangGraph   │  │  ChromaDB    │  │ PDF pipeline │
│  Planner +   │  │  retrieval   │  │  :8004       │
│  Workers     │  │  :8003       │  └──────────────┘
│  :8002       │  └──────────────┘
└──────────────┘

Infrastructure pods (shared):
  ollama     :11434   (LLM inference — GPU or CPU)
  chromadb   :8005    (vector store server mode)
  postgres   :5432    (replaces SQLite for memory + audit)
  aspire     :18888   (OTel traces + metrics + logs)
  portainer  :9000    (container management UI — Phase 18a)
  headlamp   :4466    (Kubernetes dashboard — Phase 18b)
```

---

### Service responsibilities

| Pod | Routes | Key dependency | Image base |
|---|---|---|---|
| **frontend** | `GET /` (static) | — | `node:20-alpine` → `nginx:alpine` |
| **api-gateway** | `/chat`, `/health`, `/feedback`, `/plans`, `/admin` | agentic-svc, rag-svc, voice-svc | `python:3.12-slim` |
| **voice-service** | `/audio/transcribe`, `/audio/synthesize`, `/audio/correction` | Piper `.onnx` volume, Whisper model cache | `python:3.12-slim` |
| **agentic-service** | internal gRPC/HTTP (called by api-gateway) | ollama, rag-svc, postgres | `python:3.12-slim` |
| **rag-service** | `/rag/search`, `/rag/retrieve` (internal) | chromadb, ollama (embeddings) | `python:3.12-slim` |
| **ingestion-service** | `/ingest` | rag-svc, postgres | `python:3.12-slim` |
| **chromadb** | `:8005` (ChromaDB HTTP API) | volume: `chroma_data/` | `chromadb/chroma` |
| **postgres** | `:5432` | volume: `pg_data/` | `postgres:16-alpine` |
| **ollama** | `:11434` | GPU runtime or CPU, volume: `ollama_models/` | `ollama/ollama` |
| **aspire** | `:18888` / `:4317` | — | `mcr.microsoft.com/dotnet/aspire-dashboard:9.0` |

---

### Key technical migrations

**SQLite → PostgreSQL**
Both `memory.sqlite` and `audit.sqlite` must move to Postgres so multiple pods can write
concurrently. SQLAlchemy already abstracts the DB layer — swapping the connection string is
the main change. Schema migration via Alembic.

**ChromaDB embedded → server mode**
Current: `chromadb.PersistentClient(path=...)` (in-process).
Target: `chromadb.HttpClient(host="chromadb", port=8005)` + `chromadb/chroma` Docker image.
One-line change in `src/agentic_backend/rag/retriever.py`.

**Model files as volumes**
Piper `.onnx` files and the Whisper model cache must be Docker volumes (not baked into the
image) to keep image sizes small and allow model updates without rebuilding.

**Inter-service communication**
API-gateway → other services: REST over HTTP (FastAPI `httpx` client, same pattern as Ollama calls today).
Shared state (LangGraph graph run): agentic-service is a single pod in Phase 18 — no
horizontal scaling yet, so LangGraph state stays in-process.

---

### Delivery in two sub-phases

**Phase 18a — Docker Compose (local dev)**
- One `Dockerfile` per service.
- `docker-compose.yml` at repo root wiring all pods, volumes, and env vars.
- Management UI: **Portainer CE** (`portainer/portainer-ce`) — browser UI for containers,
  images, volumes, networks, logs, and one-click restart/update.
- Replace `run_all.sh` with `docker compose up --build`.
- Smoke test: `docker compose ps` → all services healthy; `smoke_test.py` hits gateway.

**Phase 18b — Kubernetes + Helm (production-ready)**
- One `Deployment` + `Service` per pod; `ConfigMap` for env, `Secret` for tokens.
- `helm/` chart at repo root with `values.yaml` for environment overrides.
- Persistent volumes for Postgres, ChromaDB, Ollama models, Piper voices.
- Liveness + readiness probes on every service (`GET /health`).
- Horizontal Pod Autoscaler on voice-service and agentic-service.
- Management UI: **Headlamp** (`headlamp-k8s/headlamp`) — free Kubernetes dashboard,
  WSL2-compatible, supports rolling updates, log streaming, and pod restart from the UI.
  Complements **k9s** (terminal) + **Stern** (aggregated multi-pod logs).

---

### Management platform summary

| Tool | Phase | Role |
|---|---|---|
| **Portainer CE** | 18a | Web UI for Docker Compose — container list, logs, restart, image pull |
| **Headlamp** | 18b | Web UI for Kubernetes — pod health, rolling updates, log tail |
| **k9s** | 18b | Terminal K8s explorer (fast namespace/pod navigation) |
| **Stern** | 18b | Aggregated multi-pod log streaming (grep across pods) |
| **Aspire Dashboard** | both | OTel traces + metrics + structured logs (already running) |
| **React SPA — Services tab** | both | Custom health summary inside the existing UI (HTTP /health poll of each service; no container API needed) |

The **Services tab** in the React SPA is a lightweight complement (not a replacement) to
Portainer/Headlamp: it shows the health status that operations staff see inside the app
without switching to another browser tab.

---

### Out of scope for Phase 18
- Horizontal scaling of the agentic-service (LangGraph state is in-process; needs Redis-backed
  state store first — Phase 19 territory).
- GPU scheduling in Kubernetes (Ollama node affinity — operational config, not code).
- CI/CD pipeline for image builds (GitHub Actions workflow — separate DevOps track).
- Multi-tenant namespace isolation (Phase 17 OAuth prerequisite).

---

**Effort estimate:** L (Phase 18a Docker Compose) + L (Phase 18b Kubernetes).
**Recommended order:** 18a first — gives immediate value with minimal risk; 18b unlocks
production deployment and horizontal scale.

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
| Container orchestration — Docker Compose | Phase 18a (proposed) | ❌ gap |
| Kubernetes + Helm deployment | Phase 18b (proposed) | ❌ gap |
| SQLite → PostgreSQL (multi-pod DB) | Phase 18 (proposed) | ❌ gap |
| ChromaDB server mode | Phase 18 (proposed) | ❌ gap |
| Multi-tenant architecture | Not planned | ❌ gap (architecture change) |
| TimeGEN-1 forecasting | Not planned | ❌ gap (separate model) |

---

## Suggested prioritisation order

```
NOW (hotfix)
  F1  STT pre-download at setup
  F2  HF_TOKEN in setup
  F3  Strategic roadmap doc update ✅ (done in this commit)

FEATURE TRACK (sequential — each depends on the previous)
  Phase 14  Cross-conversation planning
            → plans table already exists from Phase 12
            → highest user-visible value: "resume my report from yesterday"

  Phase 15  Recursive Skill composition
            → enables complex multi-step autonomous workflows
            → depends on Phase 14 plan persistence

LANGUAGE TRACK (parallel — independent of feature track)
  Phase 16  Multilingual answer pipeline
            → Option A (translate LLM reply) first — low risk, reversible
            → Phase 13 STT already returns info.language; just wire translation
              into the Assembler output path

GOVERNANCE TRACK (parallel — enterprise readiness)
  Phase 17  Skills registry → Prompt registry → Auto-eval
            → MCP Gateway → OAuth 2.0 → RBAC
            → not gating PoC capabilities; targets production handoff

INFRASTRUCTURE TRACK (parallel — can start anytime)
  Phase 18a Docker Compose — containerise all services, add Portainer CE UI
            → replaces run_all.sh; no code changes to business logic
            → requires: SQLite → Postgres migration, ChromaDB server mode

  Phase 18b Kubernetes + Helm — production-grade orchestration
            → adds Headlamp dashboard, HPA on voice + agentic pods
            → depends on Phase 18a (images already exist)

DEPENDENCY GRAPH
  14 → 15
  16 ──────────────────────────────── independent
  17 ──────────────────────────────── independent (OAuth blocks RBAC internally)
  18a → 18b ─────────────────────── independent (blocks horizontal scale of agentic)
```
