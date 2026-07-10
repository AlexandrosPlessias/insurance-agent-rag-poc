# Observability

The stack emits OpenTelemetry traces and structured logs for every chat turn. Everything
stays local — traces go to a Docker-hosted .NET Aspire Dashboard; no data leaves the machine.

---

## Starting the Aspire Dashboard

The full-stack launcher starts it automatically:

```bash
cd src && source .venv/bin/activate
bash scripts/run_all.sh
```

Or start it alone:

```bash
bash scripts/run_observability.sh
```

Dashboard URL: **http://localhost:18888**

---

## What gets traced

Every chat turn opens a parent OTel span named `chat.turn`. Child spans are emitted for each
stage of the pipeline:

| Span | Emitted by | Key attributes |
|---|---|---|
| `planner.plan` | `agents/planner_agent.py` | `question.preview`, `planner.model`, `planner.steps`, `planner.duration_s` |
| `planner.self_critique` | `agents/planner_agent.py` | — |
| `orchestrator.execute` | `graph/orchestrator.py` | `plan.step_count` |
| `worker.execute` | `graph/orchestrator.py` | `step.skill_name`, `step.step_id` |
| `tool.<name>` | each tool in `tools/` | tool-specific attributes |
| `assembler.merge` | `agents/assembler_agent.py` | `steps.merged`, `answer.length` |

The Aspire Dashboard shows a waterfall view of all spans — useful for spotting which Skill or
Tool is slow without adding any print statements.

---

## Structured logging

All log output uses `src/agentic_backend/observability/logging.py:get_logger()`, which wraps
the standard library logger. Log format:

```
2026-07-09 14:23:01 INFO  agentic_backend.agents.planner_agent  Planner LLM returned 312 chars in 1.24s
```

Log level is controlled by `LOG_LEVEL` in `src/.env` (default: `INFO`).

> **Security:** Passwords, tokens, and PII are never logged — not even at `DEBUG`. The audit
> trail (separate from logs) records plan/step/tool events keyed by `trace_id` for compliance
> replay — it does not log message content.

---

## Audit trail

Every Plan, Step, Tool call, and feedback vote is written to `src/data/audit.db` via
`src/agentic_backend/audit/middleware.py`. Export to CSV for PowerBI:

```bash
python src/scripts/audit_export.py
```

The CSV schema:

| Column | Description |
|---|---|
| `trace_id` | Links all events for one chat turn |
| `event_type` | `plan.emitted` · `step.dispatched` · `step.completed` · `tool.called` · `feedback.received` |
| `plan_id` | UUID of the Plan (matches `plan_id` in the chat response) |
| `step_id` | Step within the Plan |
| `payload_json` | Event-specific JSON blob |
| `created_at` | ISO 8601 timestamp |

---

## Adding a custom span

```python
from agentic_backend.observability.tracing import get_tracer

tracer = get_tracer(__name__)

with tracer.start_as_current_span("my_operation") as span:
    span.set_attribute("my.key", "value")
    do_work()
```

The tracer is pre-configured to export to the local OTLP collector (`OTEL_EXPORTER_OTLP_ENDPOINT`
in `src/.env`, default `http://localhost:4317`).
