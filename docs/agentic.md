# Agentic Architecture (Phase 11)

> Capability catalogue for the Planner · Orchestrator · Workers · Tools · Skills stack introduced in Phase 11.
> Topology diagram lives in [GRAPH.md § Phase 11](GRAPH.md#phase-11--agentic-topology).
> Roadmap context: [README.md § Phase 11](../README.md#phase-11--agentic-multi-intent-architecture--feedback-).

This document is the design-of-record for the Phase 11 agentic stack. It complements
[GRAPH.md](GRAPH.md) (graph shape + diagrams). The Phase 1–10 per-node MUST / MUST-NOT
contracts are preserved in [§ 10 below](#10--legacy-phase-110-contracts).

---

## 1 · Why agentic?

The Phase 1–10 graph routes every user message to **one** of four workers. That
shape was fine for single-intent questions, but it has three structural limits:

1. **Multi-intent questions silently drop content.** *"What's the refund window
   AND the 2024 loss ratio?"* picks one branch and discards the other.
2. **Capabilities aren't reusable.** A new skill (*"summarise a customer
   complaint"*) means a new node, a new edge, and a supervisor-prompt change.
3. **Workers re-derive their own tool surface every time.** RAG, Data, and
   Report each call `vector_search` / `kpi_query` / `knowledge_base_lookup`
   through ad-hoc helpers — no shared, observable, audited tool layer.

The agentic stack solves all three by separating **planning** (which Skill, in
what order, with what dependencies?) from **execution** (run the Skills, in
parallel where possible, call their Tools, merge the results).

State-of-the-art principles applied:

- **Structured outputs end to end.** Pydantic at every agent boundary; no
  JSON-extract-from-prose anywhere downstream of the LLM.
- **Tool use, not text parsing.** Workers reach the data layer through typed
  `bind_tools` calls — never by `json.loads(model_output)`.
- **Reflection loops.** Planner self-critiques the Plan before publishing it;
  Assembler self-critiques the final answer for citation completeness.
- **Capability as data.** A Skill is a JSON-ish record loaded from disk, not a
  hard-coded graph node — registering a new Skill is one file in `app/skills/`.
- **Auditable replay.** Every Plan / Step / Tool call is one audit row keyed by
  `trace_id`; reviewers can re-execute a turn deterministically from the log.
- **Budget-aware degradation.** Orchestrator enforces `max_steps`,
  `max_tool_calls`, and `max_seconds`; overrun → graceful partial answer, never
  a 500.

---

## 2 · The five layers

```
                    ┌─────────────────────────────────────┐
                    │            chat.turn                │  ← OTel span (parent)
                    └─────┬─────────────────────────┬─────┘
                          │                         │
                          ▼                         │
                    ┌──────────────┐                │
            (1)     │   Planner    │  3B fast model │
                    │   .plan      │  + self-critique
                    └──────┬───────┘                │
                           │ Plan{steps: list[Step]}│
                           ▼                         │
                    ┌──────────────┐                │
            (2)     │ Orchestrator │  DAG walker   │
                    │  .execute    │  parallel Send │
                    └──────┬───────┘                │
                           │ for each ready Step    │
              ┌────────────┼────────────┐           │
              ▼            ▼            ▼           │
        ┌──────────┐ ┌──────────┐ ┌──────────┐     │
   (3)  │  Worker  │ │  Worker  │ │  Worker  │     │
        │  shell   │ │  shell   │ │  shell   │     │
        └─────┬────┘ └─────┬────┘ └─────┬────┘     │
              │            │            │           │
              │  ┌─────────┴─┐  loads Skill spec ──┘
              │  │ Skill (4) │  {prompt, tools,
              │  │           │   input/output schema}
              │  └─────┬─────┘
              │        │ bind_tools(LLM)
              ▼        ▼
        ┌─────────────────────┐
   (5)  │       Tools         │  vector_search · kpi_query
        │  (atomic, typed)    │  knowledge_base_lookup
        └─────────┬───────────┘  clarifier_check · audit_write
                  │ structured results
                  ▼
        ┌──────────────────────┐
        │    Assembler         │  H3 sections · unified citations
        │    (validator)       │  self-critique on completeness
        └──────────┬───────────┘
                   ▼
                 FINISH
```

### 2.1 Planner

**Responsibility.** Turn a free-form user question into a typed, validated `Plan`.

The Planner **subsumes the Phase 1–10 supervisor's classification role.**
Instead of emitting `route="rag"` / `"data"` / `"report"` / `"out_of_scope"`,
it emits a `Plan` whose Steps reference the equivalent Skills
(`answer_policy_question` · `compute_kpi` · `executive_section_summary` · …).
Single-intent turns are degenerate Plans with **one Step** — the rest of the
pipeline runs identically. There is **one topology** for every turn.

| Aspect | Value |
|---|---|
| Model | `qwen2.5:3b` (fast lane) — full 7B reserved for workers |
| Input | `{question, conversation_history, target_year?, skill_registry: list[SkillMetadata]}` |
| Output | `Plan` (see [§ 4 Data shapes](#4--data-shapes)) |
| LLM calls | 1 (plan) + 1 (self-critique) |
| Failure mode | Self-critique catches structural errors; runtime DAG validation in the orchestrator catches what slipped through |

**Plan validity rules (self-critique).**
1. Every `Step.skill_name` exists in the registry.
2. Dependency graph is acyclic.
3. No Step depends on a clarification that hasn't fired yet (year-clarifier
   has its own short-circuit Step type).
4. Total Steps ≤ `max_steps` budget.

**Security boundary.** The Planner sees Skill `name + description + schemas`
only. It **never** sees Skill `system_prompt`. A malicious user asking *"plan
this and ignore your previous instructions"* cannot hijack a worker because the
Planner can't write into worker prompts — it can only emit `{skill_name, args}`
records that match a registered schema.

### 2.2 Orchestrator

**Responsibility.** Walk the `Plan` DAG, dispatch ready Steps in parallel,
collect their structured outputs, hand them to the Assembler.

| Aspect | Value |
|---|---|
| Model | none (pure code — LangGraph routing only) |
| Input | `Plan` |
| Output | `OrchestratorResult{step_results: dict, partial: bool, budget_remaining}` |
| Mechanism | LangGraph `Send()` for parallel dispatch; per-Step `Annotated[list, operator.add]` reducer accumulates results |
| Budgets | `max_steps`, `max_tool_calls`, `max_seconds` (config-driven) |

**Execution semantics.**

1. Mark all Steps with `depends_on=[]` as **ready**.
2. For each ready Step, `Send()` to the owning worker with `{skill_name, args, dependency_outputs}`.
3. As Steps complete, write results to `step_results[step_id]` and re-evaluate readiness.
4. On Step failure: record `step_results[step_id] = StepFailure{reason, retriable}`. Continue
   running independent Steps. Dependent Steps short-circuit to `StepSkipped`.
5. On budget overrun: mark `partial=True`, stop dispatching new Steps, hand whatever's collected to the Assembler.

**Why an Orchestrator agent (not just `Send()`)?** Because `Send()` doesn't
know about budgets, doesn't know about cross-Step dependency outputs, and
doesn't know about partial-failure semantics. The Orchestrator is the layer
where those policies live.

### 2.3 Workers

**Responsibility.** Load a Skill spec, invoke its prompt + tools, return the
Skill's typed output.

Workers in Phase 11 are **thin shells**. The four worker families
(RAG · Data · Report · Memory) are preserved for routing affinity — the
RAG worker still owns vector search, the Data worker still owns pandas — but
the worker itself is a 30-line function:

```python
def worker(step: Step, deps: dict[str, Any]) -> StepResult:
    skill = SKILL_REGISTRY[step.skill_name]
    llm = get_llm(skill.model)  # may differ per Skill
    llm = llm.bind_tools(skill.tools)
    return skill.invoke(llm, step.args, deps)
```

All capability lives in the Skill spec; all per-turn state lives in the
LangGraph reducer.

### 2.4 Skills

**A Skill is a reusable capability bundle.** Schema:

```python
class Skill(BaseModel):
    name: str                          # unique, kebab-case
    description: str                   # what the Planner sees (1-2 lines)
    owner_worker: Literal[
        "rag", "data", "report", "memory", "any"
    ]
    model: str = "qwen2.5:7b"          # which Ollama tag to use
    system_prompt: str                 # NOT exposed to Planner
    tools: list[Tool]
    input_schema: type[BaseModel]
    output_schema: type[BaseModel]
```

**Initial Skill set** (`poc/app/skills/`):

| Skill | Owner | Tools | Purpose |
|---|---|---|---|
| `answer_policy_question` | rag | `vector_search`, `clarifier_check` | Year-scoped grounded RAG answer with citations |
| `compute_kpi` | data | `kpi_query`, `clarifier_check` | Typed `Operation` → pandas executor → narrative + table |
| `executive_section_summary` | report | `kpi_query`, `vector_search`, `knowledge_base_lookup` | One section of the Phase 9 executive pipeline |
| `clarify_year` | any | (none) | Emits a year-clarification question; resumes on next turn |
| `out_of_year_fallback` | any | (none) | Names nearest covered years; refuses to invent 2023 data |
| `decline` | any | (none) | Politely refuses questions unrelated to insurance or ACME — no LLM call, no tools, canned message |

**Registration.** Adding a new Skill is a **one-file PR**:

```python
# poc/app/skills/summarise_complaint.py
from app.llm import load_prompt
from app.skills import Skill

skill = Skill(
    name="summarise-complaint",
    description="Summarise a customer complaint thread for a given audience.",
    owner_worker="rag",
    model="qwen2.5:7b",
    system_prompt=load_prompt("skills/summarise_complaint"),
    input_fields={
        "complaint_id": "str – the complaint thread ID",
        "target_audience": "'customer' | 'ombudsman'",
    },
    tools_used=["knowledge_base_lookup", "vector_search"],
)
```

Prompt template at `poc/app/llm/prompts/skills/summarise_complaint.txt`.

The `skills/__init__.py` registry auto-discovers any module exporting a
`skill: Skill` symbol. **No changes to Planner / Orchestrator / Workers required.**

### 2.5 Tools

**A Tool is an atomic, side-effect-free function with a Pydantic schema.**
Tools are what Workers actually call to touch the data layer.

**Initial Tool set** (`poc/app/tools/`):

| Tool | Schema (input → output) | Span name | Notes |
|---|---|---|---|
| `vector_search` | `{query, year_filter?}` → `list[Chunk]` | `tool.vector_search` | Wraps the Phase 1/7 retriever |
| `kpi_query` | `Operation` → `DataFrame` | `tool.kpi_query` | The Phase 8 executor — unchanged |
| `knowledge_base_lookup` | `{doc_id, section?}` → `str` | `tool.knowledge_base_lookup` | Direct PDF-section fetch (bypasses vector store) |
| `clarifier_check` | `{question, target_year?}` → `ClarifierVerdict` | `tool.clarifier_check` | Phase 7 year-clarifier as a callable |
| `audit_write` | `{event_type, payload}` → `None` | `tool.audit_write` | Persists an audit row keyed by current `trace_id` |

**Binding to the LLM.** Tools are exposed via
`langchain_core.tools.tool` decorators + `llm.bind_tools([...])` so the model
emits typed function calls, not free-text JSON. No `json.loads` in the worker
layer.

**Side-effect discipline.** Tools are **read-only by default**. `audit_write`
is the one mutating Tool; it appends to the audit log and is invoked by the
worker shell after the Skill returns, not by the Skill itself. This keeps
Skills replayable.

### 2.6 Assembler

**Responsibility.** Concatenate Step outputs into a single coherent answer.

- Inputs sorted by `Plan.steps` order (deterministic).
- Each Step's output rendered under an H3 header derived from
  `Step.args.heading` (Planner-provided) or `Skill.name` (fallback).
- Citations from all Steps deduplicated, renumbered, merged into a single
  block at the end.
- **Self-critique sub-call** checks: every numeric claim has a citation, every
  Step's output was rendered, no Step was silently dropped.
- On `partial=True` from the Orchestrator: prepends a `⚠ Partial answer` badge
  naming which Steps were skipped and why.

**Single-Step Plans are no-op pass-throughs** — the Assembler still runs
(uniform OTel + audit shape) but skips the H3-header / citation-merge logic
and emits the Step output verbatim. Cost: one cheap LLM call for the
completeness critique, no markdown gymnastics.

---

## 3 · Observability + audit

### OTel span hierarchy

```
chat.turn (trace root)
├── planner.plan
│   └── planner.self_critique
├── orchestrator.execute
│   ├── step.<id_1>
│   │   ├── worker.<rag|data|report>.invoke
│   │   ├── tool.vector_search
│   │   └── tool.audit_write
│   ├── step.<id_2>
│   │   └── …
│   └── step.<id_3>
└── assembler.merge
    └── assembler.self_critique
```

Aspire renders this as one collapsible tree per chat turn. Every span carries:
`trace_id` · `step_id` (where applicable) · `skill_name` · `tool_name` ·
`tokens_in` · `tokens_out` · `latency_ms` · `model_id`.

### Audit-event taxonomy

All events land in the existing `audit_events` table ([poc/app/audit/schema.sql](../poc/app/audit/schema.sql)),
keyed by `trace_id`. No new tables.

| `event_type` | `payload_json` shape | Source |
|---|---|---|
| `planner.plan` | `{plan_id, steps: [...], rationale, n_steps}` | `agents/planner_agent.py` |
| `orchestrator.step` | `{step_id, skill_name, status, latency_ms}` | `graph/orchestrator.py` |
| `feedback.received` | `{plan_id, trace_id, score, comment, user_id, updated_at}` | `api/routes/feedback.py` |

All Phase 1–10 event types (`supervisor.route`, `rag.retrieve`, `validator.judge`, etc.) are
unchanged — Phase 11 adds three new types on top; it does not replace the existing taxonomy.
The full list is the canonical source: [`poc/app/audit/events.py`](../poc/app/audit/events.py).

### Replay

Given a `trace_id` from the audit log, a reviewer can:
1. Read all `audit_events` rows for that `trace_id`, ordered by `ts`.
2. Reconstruct the Plan from `plan.emitted`.
3. Re-run each Step against the recorded Tool outputs (no LLM re-call needed
   — the deterministic part replays from the audit alone).
4. For full re-execution including LLM calls, the recorded prompts + `model_id`
   + temperature=0 path through the Skill spec gives bit-exact reproduction
   against the same model checkpoint.

---

## 4 · Data shapes

```python
from typing import Annotated, Any, Literal
from pydantic import BaseModel, Field

# ---------- Plan ----------

class Step(BaseModel):
    step_id: str                       # planner-assigned, unique within the Plan
    skill_name: str                    # must exist in the Skill registry
    args: dict[str, Any]               # must match Skill.input_schema
    depends_on: list[str] = []         # other step_ids; cycles are rejected
    heading: str | None = None         # H3 header in the final answer (else: Skill.name)

class Plan(BaseModel):
    plan_id: str                       # uuid4
    steps: list[Step]
    rationale: str                     # one-liner the Planner writes for the audit log

# ---------- Step results ----------

class StepSuccess(BaseModel):
    kind: Literal["ok"] = "ok"
    step_id: str
    output: dict[str, Any]             # matches Skill.output_schema
    citations: list["Citation"] = []
    tokens: dict[str, int]             # {in, out}
    latency_ms: int

class StepFailure(BaseModel):
    kind: Literal["failed"] = "failed"
    step_id: str
    reason: str
    retriable: bool
    exception_class: str

class StepSkipped(BaseModel):
    kind: Literal["skipped"] = "skipped"
    step_id: str
    reason: Literal["dependency_failed", "budget_exhausted"]

StepResult = Annotated[
    StepSuccess | StepFailure | StepSkipped,
    Field(discriminator="kind"),
]

# ---------- Orchestrator ----------

class OrchestratorResult(BaseModel):
    plan_id: str
    step_results: dict[str, StepResult]
    partial: bool
    budget_remaining: dict[str, int]   # {steps, tool_calls, seconds}

# ---------- Skill metadata (what the Planner sees) ----------

class SkillMetadata(BaseModel):
    name: str
    description: str
    input_schema: dict                 # JSON Schema dump of the Pydantic model
    output_schema: dict
    owner_worker: str
```

---

## 5 · Security guarantees

| Threat | Mitigation |
|---|---|
| User jailbreaks the Planner into hijacking a worker | Planner sees Skill `name + description + schemas` only — never `system_prompt`. Worst case: Planner emits a Step with valid `skill_name` but absurd `args`; Skill's `input_schema` rejects it. |
| Cross-Step output pollutes a downstream worker's prompt with prompt-injection text | Tool outputs flow through a `sanitise_dependency_output` passthrough (strip control characters · cap length · re-anchor with XML tags) before becoming inputs to dependent Steps. |
| Tool execution leaks PII into Aspire / audit log | Tool span attributes record `output_sha` (sha256 of the result) **not the result itself** when the Tool's `redact_in_telemetry=True` flag is set. The result still flows to the worker — just not to telemetry. |
| Malicious Skill installed via a typo-squat | Skill registry only loads modules under `poc/app/skills/`; `__init__.py` enforces an allowlist of expected Skill names; CI fails if a Skill name appears that isn't on the allowlist. |
| Budget overrun used as a DOS vector | Per-turn budgets are enforced **before** the planner runs (max question length) and **inside** the orchestrator (max steps · tool calls · seconds). |

---

## 6 · Extension playbook

### Add a new Skill

1. Create `poc/app/skills/<skill_name>.py` with a `skill: Skill` export.
2. Drop the system prompt into `poc/app/llm/prompts/skills/<skill_name>.txt`.
3. (If new Tools are needed) implement them under `poc/app/tools/`.
4. Add a smoke-test scenario in `poc/scripts/smoke_test.py` that triggers
   the Planner into emitting a Step with this Skill.
5. Update [docs/agentic.md § 2.4](#24-skills) Skill table.

No changes to Planner, Orchestrator, Worker shells, or the graph.

### Add a new Tool

1. Implement under `poc/app/tools/<tool_name>.py` with a `@tool` decorator
   exposing a Pydantic input schema.
2. Export from `poc/app/tools/__init__.py`.
3. Add to the Skill specs that need it.
4. Confirm a new OTel span name `tool.<tool_name>` appears in Aspire.

### Add a new Worker family

Rare — only needed when a Skill needs a fundamentally different runtime
(e.g. a vision worker for image inputs). Steps:

1. Implement the worker shell under `poc/app/agents/<worker>_agent.py`.
2. Wire it into [poc/app/graph/builder.py](../poc/app/graph/builder.py) as a
   new graph node.
3. Add `owner_worker="<worker>"` to the relevant Skills.

---

## 7 · Budgets + degradation

| Budget | Default | Effect on overrun |
|---|---|---|
| `max_steps` | 8 | Planner self-critique rejects the Plan; if violated at runtime, Orchestrator early-stops |
| `max_tool_calls` | 32 (across all Steps) | Worker shell refuses further Tool calls; Step returns `StepFailure(reason="tool_budget")` |
| `max_seconds` | 60 | Orchestrator cancels in-flight Steps via `asyncio.timeout`, marks `partial=True` |
| `max_question_length` | 4 000 chars | Rejected pre-Planner with HTTP 413 |

All budgets are config-driven via `poc/app/config.py` → `Settings.agentic`
(new namespace).

---

## 8 · Future optimisation: N=1 bypass

The uniform pipeline costs ~200 ms over Phase 1–10 for single-intent turns
(one Planner call on the 3B model + one Orchestrator round-trip + one no-op
Assembler call). This is **acceptable by default** because it buys consistent
OTel spans, audit rows, and replay semantics across every turn.

If a real production latency target (e.g. <1 s p95) ever makes that 200 ms
load-bearing, the staged escape hatch is **opt-in behind**
`settings.agentic.fast_path=true`:

1. **Heuristic Planner short-circuit.** If the question contains no
   multi-intent markers (`" AND "`, `";"`, `" & "`, more than one `?`),
   synthesise a single-Step Plan from a regex-based route classifier
   instead of calling the LLM. Cost: ~30 ms. **Audit + OTel shape
   unchanged** — the Plan still gets emitted with `source="heuristic"`.
2. **Orchestrator fast-lane.** For Plans with `len(steps) == 1`, the
   Orchestrator can skip the `Send()` round-trip and call the worker
   inline. Cost: ~20 ms. The `step.dispatched` / `step.completed` audit
   rows still fire.
3. **Assembler skip flag.** When the Plan has one Step AND the self-critique
   already ran inside the worker, the Assembler can be elided. Saves the
   final critique call. Cost: ~50 ms. Adds an `assembler.skipped` audit row.

**Do not implement these speculatively.** The point of the uniform pipeline
is observability + replay parity. Each escape hatch dilutes that promise
and adds a code path that needs maintenance. Defer until measured latency
demands it, and ship them one at a time with a clear before/after benchmark
in the PR description.

---

## 9 · What's deferred to later phases

The four big follow-ups now have phase numbers — see the main
[README roadmap](../README.md) for functional bullets:

- **Phase 12 — Human-in-the-Loop & Telegram channel.** Long-running plans
  with approval gates between Steps; approval round-trip over Telegram (or
  Slack / Teams via a shared `ApprovalChannel` interface).
- **Phase 13 — Multi-modal voice.** Audio input (Whisper.cpp) + audio output
  (Piper TTS) as first-class modalities behind new Tools.
- **Phase 14 — Cross-conversation planning.** Plans become first-class
  memory objects that span sessions; resume-tokens, multi-user participants,
  schema migration on Skill evolution.
- **Phase 15 — Recursive Skill composition.** Skills can emit sub-Plans;
  the Orchestrator becomes recursive with `max_recursion_depth` + cycle
  detection.

Still phase-less (no design yet):

- **Distributed worker execution** — workers run in-process today.
- **Skill marketplace UI · Skill versioning · A/B comparison.**
- **Image / vision Tools** (Phase 13 covers audio only).

---

## 10 · Legacy Phase 1–10 contracts

> **Superseded by Phase 11.** The supervisor → single-worker routing below was the active
> topology through Phase 10. Phase 11 replaced it with the Planner · Orchestrator · Workers ·
> Skills stack documented in §§ 1–9 above. The per-node contracts and decision matrix remain
> accurate for the legacy code paths that continue to run inside Phase 11 worker nodes.

### Routes

The supervisor classified every message into exactly one of six routes:

| Route | Picked when | Terminal node | LLM calls |
|---|---|---|---|
| `rag` | Year resolved **and** policy content question | `validator` (1-retry loop) | 3+ (reformulate + answer + validator, ×2 on retry) |
| `report` | "summary" / "report" / "breakdown" language | `report` | 1–3 |
| `data` | Quantitative question over the KPI dataset | `data.node` | 1 (planner only — executor is pure pandas) |
| `out_of_scope` | Greetings, chit-chat, non-insurance | `decline.canned` | 0 |
| `needs_clarification` | RAG-ish question but no resolvable year | `clarifier.ask` | 1 |
| `out_of_year` | Year named but not in `kb_covered_years` | `fallback.out_of_year` | **0** |

### Decision matrix

| Question has year? | Year covered? | LLM classifies as | Final route |
|---|---|---|---|
| No, history has none | — | `rag` | `needs_clarification` *(override)* |
| No, history has one | covered | `rag` | `rag` (year inherited) |
| Yes | covered | `rag` | `rag` |
| Yes | covered | `report` | `report` |
| Yes | covered | `out_of_scope` | `out_of_scope` |
| Yes | **not** covered | (skipped) | `out_of_year` *(no LLM call)* |
| No | — | `report` | `report` |
| No | — | `out_of_scope` | `out_of_scope` |

Two hard overrides fire after LLM classification:
1. `target_year ∉ covered_years` always wins — the supervisor never calls the LLM for a 2023 question.
2. `rag` + no resolvable year → `needs_clarification`.

### Per-node contracts

**`supervisor.classify`**

| MUST | MUST NOT |
|---|---|
| Inject `today` and `covered_years` into state at entry | Call the embedding model or the retriever |
| Run deterministic regex year-extraction first | Generate the final user-facing answer |
| Short-circuit to `out_of_year` before any LLM call when year not covered | Make more than one LLM call per turn |
| Override `rag → needs_clarification` when no year is resolvable | Persist anything outside its single `supervisor.route` audit event |

**`rag.node`**

| MUST | MUST NOT |
|---|---|
| Honour `where_filter={"year": target_year}` when `state.target_year` is set | Ask the user any meta-conversational question |
| Run reformulate → retrieve → answer | Refuse a question because of a year gap (supervisor's job) |
| Pass `chunks` and `draft_answer` to the validator | Skip the validator |
| Write `rag.retrieve` and `rag.answer` audit events | Persist a final answer directly to memory |

**`validator.judge`**

| MUST | MUST NOT |
|---|---|
| Judge groundedness + citation correctness against retrieved chunks | Run on clarifier / fallback / decline output |
| Increment `retry_count` on first failure; accept as unverified after one retry | Loop indefinitely |
| Emit `validator.judge` audit event with the full validation dict | Generate or rewrite the final answer |

**`clarifier.ask`**

| MUST | MUST NOT |
|---|---|
| Emit exactly one short clarifying question | Attempt to answer the original question |
| Fall back to a deterministic templated question if the LLM call fails | Retrieve chunks |
| End the turn | Loop back to the supervisor |

**`fallback.out_of_year`**

| MUST | MUST NOT |
|---|---|
| Name the nearest covered years (one below, one above) | Call any LLM |
| Be templated and reproducible | Retrieve chunks |
| End the turn | Suggest a year not in `kb_covered_years` |

**`decline.canned`**

| MUST | MUST NOT |
|---|---|
| Return the static decline message | Call any LLM |
| End the turn | Engage with the off-topic content |

**`report.node`**

| MUST | MUST NOT |
|---|---|
| Dispatch to `executive.build_executive_report(year)` when `target_year` is set | Run through the validator |
| Render Markdown + chart inline (legacy path, no `target_year`) | Loop or retry |
| Set `report_kind` / `report_year` / `report_run_id` on state for DOCX/PDF/MD downloads | Let the LLM decide risk severity — that's `thresholds.py` only |

**`data.node`**

| MUST | MUST NOT |
|---|---|
| Emit exactly one typed `Operation` JSON from the planner LLM | Let the LLM generate executable code |
| Run the executor against `KpiDataset.df` with schema-aware guards | Aggregate a rate/snapshot metric with `sum` |
| Filter out `is_rollup` rows by default to avoid double-counting | Touch year 2023 (symmetric with `out_of_year`) |
| Write `data.plan` and `data.execute` audit events | Validate via `validator.judge` |

---

## 11 · References

- Graph shape + diagrams: [GRAPH.md](GRAPH.md)
- Roadmap: [README.md § Phase 11](../README.md#phase-11--agentic-multi-intent-architecture--feedback-)
- Audit schema: [poc/app/audit/schema.sql](../poc/app/audit/schema.sql)
- LangGraph `Send()` reference: <https://langchain-ai.github.io/langgraph/concepts/low_level/#send>
