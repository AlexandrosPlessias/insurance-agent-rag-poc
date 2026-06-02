# Agent Topology — Design Rationale

> Why the supervisor, clarifier, fallback, RAG, and validator are **separate nodes** in the LangGraph state machine, rather than branching logic packed inside the RAG agent.

This doc captures the design intent so future readers don't refactor the topology into something smaller-looking but operationally worse.

For the rendered diagram and per-node reference, see [GRAPH.md](../GRAPH.md). For the implementation, see [poc/app/graph/](../poc/app/graph/).

---

## 1. The six routes

The supervisor classifies every incoming user message into exactly one of six routes:

| Route | Picked when | Terminal node | LLM calls in this turn |
|---|---|---|---|
| `rag` | Year is resolved (from question or recent history) **and** question is about policy content | `validator` (with 1-retry to `rag`) | 3+ (reformulate + answer + validator, ×2 on retry) |
| `report` | Question contains words like "summary", "report", "overview", "breakdown" about a policy document | `report` | 1 (structured extractor) |
| `data` | Quantitative or analytical question over the KPI dataset — named metric, quantitative verb (`compare`, `trend`, `by channel`, `vs`), or numeric comparison | `data.node` | 1 (planner only — executor is pure pandas) |
| `out_of_scope` | Greetings, math, chit-chat, non-insurance | `decline.canned` | 0 (templated reply) |
| `needs_clarification` | Question is RAG-ish but no year mentioned and history can't resolve one | `clarifier.ask` | 1 small (with deterministic fallback if it fails) |
| `out_of_year` | A year was named (regex) but it isn't in `kb_covered_years` | `fallback.out_of_year` | **0** (no LLM call at all) |

`needs_clarification` and `out_of_year` are the Phase 7 additions; `data` is the Phase 8 addition. The rest predates them.

> **Phase 10 (PoC presentation deck)** is intentionally absent from this table. It's a non-runtime build artefact — a `python-pptx`-generated stakeholder deck assembled from [`docs/presentation/deck.md`](presentation/deck.md) + [`docs/screens/`](screens/) by [`poc/scripts/build_pptx.py`](../poc/scripts/build_pptx.py). No node in the graph, no operational impact, no audit event. Lives entirely outside the request/response path.

---

## 2. Why these are separate nodes (and not internal RAG branches)

The natural temptation is "RAG owns everything year-related — it has the retriever, so let it figure out missing/bad years." We chose against it for six concrete reasons.

### 2.1 Zero-LLM short-circuit for `out_of_year`

The supervisor decides `target_year ∉ covered_years` **before** any LLM call. A 2023 question costs **one** supervisor LLM call total (and on a future deterministic-supervisor pass, zero).

If the same logic lived inside RAG, that 2023 question would pay:

| Step | Cost |
|---|---|
| `rag.reformulate` | 1 LLM call |
| `rag.retrieve` (with `where={"year": 2023}`) | 1 embedding pass + Chroma query that returns 0 chunks |
| `rag.llm.invoke` | 1 LLM call against an empty context — model hallucinates or refuses |
| `validator.judge` | 1 LLM call to detect the hallucination |
| Possible retry | another 1–2 LLM calls |

We'd be paying 3–5 LLM calls to learn what the supervisor already knew from the question.

### 2.2 Wrong-year retrieval is worse than no retrieval

A `where_filter={"year": 2023}` against a KB that has no 2023 documents returns zero chunks. An LLM handed an empty context tends to:

- hallucinate from its training data (the worst failure mode for a compliance product), or
- emit a generic non-answer that the validator might or might not catch.

The validator is a backstop, not a guarantee. The fallback node sidesteps the failure altogether: the user gets a deterministic, accurate "I don't cover 2023, my range is 2020 / 2021 / 2022 / 2024" message instead of a confidently-wrong answer.

### 2.3 Validator semantics break on meta-conversation

The validator's contract is **groundedness + citation correctness against retrieved chunks**. Clarifier and fallback messages have **no chunks** — they are meta-conversational ("which year?", "I don't have that year"). Running the validator on them is nonsensical:

- `grounded` against what?
- `citations_ok` against zero citations is vacuously true (or false, depending on parsing) — neither answer is useful.

Routing them as terminal nodes lets the validator stay narrow.

### 2.4 No retry loop on these turns

RAG has a 1-retry loop on validator failure. Clarifier and fallback are **definitive turn endings** — they should not retry. If they were inside RAG:

- `route_from_validator` would need to introspect *which kind* of RAG turn we're in to decide whether to retry.
- The retry decision leaks intent across files.
- A future contributor refactoring the retry logic would have to remember the carve-outs.

By making them separate nodes that go straight to `END`, the retry edge only fires on actual RAG attempts.

### 2.5 Audit + telemetry stay countable

Compliance reviewers ask questions like:

- *"How many requests bounced off the 2023 gap this quarter?"*
- *"How often does the clarifier fire — does it correlate with new users?"*
- *"What's our refusal rate (out_of_scope vs out_of_year)?"*

All three answers are one SQL query against `audit_events.event_type` or one filter in Aspire on `supervisor.route`:

```sql
SELECT COUNT(*) FROM audit_events
WHERE event_type = 'year_fallback' AND ts >= '2026-01-01';
```

If clarifier/fallback lived inside RAG, every count would become a `json_extract(payload_json, '$.some_field')` query against the `rag.answer` event — slower, fragile to payload-schema changes, and not greppable in Aspire's filter UI.

### 2.6 The graph topology is the source of truth

[poc/app/graph/builder.py](../poc/app/graph/builder.py) lists every possible outcome at a glance:

```python
builder.add_conditional_edges(
    "supervisor",
    route_from_supervisor,
    {
        "rag": "rag",
        "report": "report",
        "out_of_scope": "decline",
        "needs_clarification": "clarifier",
        "out_of_year": "fallback",
    },
)
```

A reader sees the five outcomes in five lines. Folding the Phase 7 routes into RAG means that same reader has to open `rag_agent.py` and trace the internal branching to learn what really happens to their question — a worse mental model for everyone after the original author.

---

## 3. Node contracts (what each node MUST and MUST NOT do)

This is the rule that makes the topology stable. If a future change pulls a node out of its contract, the design erodes — refer back here.

### `supervisor.classify`

| MUST | MUST NOT |
|---|---|
| Inject `today` and `covered_years` into state at entry | Call the embedding model or the retriever |
| Run the deterministic regex year-extraction first | Generate the final user-facing answer |
| Short-circuit to `out_of_year` *before* any LLM call when `target_year ∉ covered_years` | Make more than one LLM call per turn |
| Override `rag → needs_clarification` when no year is resolvable | Persist anything (memory or audit) outside its single `supervisor.route` event |

### `rag.node`

| MUST | MUST NOT |
|---|---|
| Honour `where_filter={"year": target_year}` when `state.target_year` is set | Ask the user any meta-conversational question |
| Run reformulate → retrieve → answer | Refuse a question because of the year gap (that's the supervisor's job) |
| Pass `chunks` and `draft_answer` to the validator | Skip the validator |
| Write `rag.retrieve` and `rag.answer` audit events | Persist a final answer directly to memory (validator owns that) |

### `validator.judge`

| MUST | MUST NOT |
|---|---|
| Judge groundedness + citation correctness against the retrieved chunks | Run on clarifier/fallback/decline output (the graph never routes there) |
| Increment `retry_count` on first failure; accept as unverified after one retry | Loop indefinitely |
| Emit `validator.judge` audit event with the full validation dict | Generate or rewrite the final answer |

### `clarifier.ask`

| MUST | MUST NOT |
|---|---|
| Emit exactly **one** short clarifying question | Attempt to answer the original question |
| Fall back to a deterministic templated question if the LLM call fails | Retrieve chunks |
| End the turn (graph goes to END) | Loop back to the supervisor |

### `fallback.out_of_year`

| MUST | MUST NOT |
|---|---|
| Name the nearest covered years (one below, one above) | Call any LLM |
| Be templated and reproducible | Retrieve chunks |
| End the turn | Suggest a year that isn't in `kb_covered_years` |

### `decline.canned`

| MUST | MUST NOT |
|---|---|
| Return the static decline message | Call any LLM |
| End the turn | Engage with the off-topic content |

### `report.node`

`report.node` is the dispatch point: with `target_year` present it
hands off to the Phase 9 executive pipeline; without it falls back
to the legacy Phase 3 single-policy summary.

| MUST | MUST NOT |
|---|---|
| Dispatch to `app.reporting.executive.build_executive_report(year)` when `target_year` is set (Phase 9) | Run through the validator (report turns ship Markdown + downloads, not a chunk-grounded answer) |
| Render Markdown + chart inline (legacy path) | Loop or retry |
| For Phase 9: set `report_kind` / `report_year` / `report_run_id` on the returned state so the UI renders DOCX / PDF / MD download buttons | Have the LLM decide risk severity — that's `thresholds.py` only |
| For Phase 9: write a `report.generate` audit row carrying `kind='executive'` plus the `ReportDocument.as_audit_payload()` summary (run id, csv hash, severity histogram, recommendation count) | Build the report from scratch on every download — but for v1 we do; production would cache by `(year, csv_sha, git_sha)` |

### `data.node`

| MUST | MUST NOT |
|---|---|
| Emit exactly one typed `Operation` JSON from the planner LLM | Let the LLM generate executable code — the executor is hand-written pandas, the LLM only emits typed JSON |
| Run the executor against `KpiDataset.df` with schema-aware guards (`year_gap`, `invalid_aggregation`, `unknown_metric`, `unknown_dimension_value`, `empty_result`) | Aggregate a rate or snapshot metric with `sum` — the executor refuses on metric kind |
| Filter out `is_rollup` rows by default to avoid double-counting | Touch year 2023 — symmetric with Phase 7's RAG `out_of_year` (refuses with `reason="year_gap"`) |
| Carry `last_data_operation` from state into the planner as drill-down context | Validate via `validator.judge` — data turns ship a Markdown answer + Operation expander, not a chunk-grounded answer |
| Write both `data.plan` and `data.execute` audit events (including failure cases with the typed `reason`) | Re-render previous results — every turn re-runs the planner against the current question |
| Render narrative + Markdown table + Operation expander as the assistant message | Persist beyond the turn except via `last_data_operation` (which feeds the next turn's planner) |

---

## 4. Decision matrix — which route fires when

This is the supervisor's logic in tabular form. The implementation is in [poc/app/graph/supervisor.py](../poc/app/graph/supervisor.py).

| Question contains a year? | Year is in `kb_covered_years`? | LLM classified as | Final route |
|---|---|---|---|
| No, and history has none | — | `rag` | `needs_clarification` *(override)* |
| No, but history has one | covered | `rag` | `rag` (target_year inherited) |
| Yes | covered | `rag` | `rag` |
| Yes | covered | `report` | `report` |
| Yes | covered | `out_of_scope` | `out_of_scope` |
| Yes | not covered | (skipped) | `out_of_year` *(deterministic, no LLM)* |
| No | — | `report` | `report` (no year context needed for a generic summary) |
| No | — | `out_of_scope` | `out_of_scope` |

Two overrides happen after the LLM classification:

1. **`target_year ∉ covered_years` always wins.** The supervisor never asks the LLM to classify a 2023 question — it short-circuits.
2. **`rag` + no resolvable year → `needs_clarification`.** A RAG question without a year is the textbook case for asking back.

---

## 5. Counter-argument — when would we fold them in?

We would only collapse the topology if all of these were true:

- LLM calls became free (no token cost, sub-100ms latency).
- The validator could be trained to detect "no chunks retrieved → say I don't have that year" reliably.
- We had a single-author codebase forever and didn't need other readers to trace the flow.

None of those are true today. If two of them flip in the future (e.g. local sub-second models + a stronger validator), the conversation can re-open. Until then, the five-route topology is the right shape.

---

## 6. Adding a new route in the future

If a future phase needs another route (e.g. `talk_to_data` in Phase 8), the playbook is:

1. Add the literal to [`Route`](../poc/app/graph/state.py).
2. Add the destination key to the conditional-edges dict in [`builder.get_graph`](../poc/app/graph/builder.py).
3. Implement the node as its own file under [`poc/app/graph/`](../poc/app/graph/) or [`poc/app/agents/`](../poc/app/agents/) — never inside `rag_agent.py` or `report_agent.py`.
4. Decide whether the node is terminal (most are) or feeds back into the supervisor for a multi-turn pattern.
5. Add a new `event_type` constant in [`poc/app/audit/events.py`](../poc/app/audit/events.py) and emit it from the node.
6. Update [GRAPH.md](../GRAPH.md), the stepper in [`streamlit_app.py`](../poc/app/ui/streamlit_app.py), and this doc's tables.

The supervisor decides; each route owns its node; the topology stays flat. That's the whole rule.
