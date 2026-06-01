"""Phase 8 Talk-to-Data agent.

Three-step pipeline, all in one node:

    question + dataset schema --> planner LLM --> Operation JSON
                                                     |
                                                     v
                                              executor (pandas)
                                                     |
                                                     v
                                  narrative + Markdown table + Operation
                                  expander payload (returned via state)

The LLM never emits executable code. Its single job is to translate
a question into a typed Operation; the executor is the only thing
that touches pandas. Schema guards in `app.data.executor` enforce
domain rules (no sum on rates, no 2023, etc.) before the answer
is rendered.

When the executor refuses (OperationViolation), the node returns a
templated apology referencing the typed reason so the user gets a
specific diagnostic instead of a generic failure.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from datetime import date

from langchain_core.messages import HumanMessage, SystemMessage

from app.audit import events as audit_events
from app.audit.middleware import record as audit_record
from app.data import (
    ExecutionResult,
    Filters,
    Operation,
    OperationViolation,
    execute,
    get_dataset,
)
from app.graph.state import GraphState
from app.llm import load_prompt
from app.llm.ollama_client import get_llm
from app.observability.logging import get_logger
from app.observability.metrics import track_node
from app.observability.tracing import annotate_request_span, get_tracer

log = get_logger(__name__)
tracer = get_tracer(__name__)

PLANNER_PROMPT_TEMPLATE = load_prompt("data_planner")

_MAX_TABLE_ROWS = 20


# ---------------------------------------------------------------------
# Planner
# ---------------------------------------------------------------------

def _build_planner_prompt(
    today: str,
    previous_operation: dict | None = None,
) -> str:
    """Format the planner prompt with the live schema + dimensions.

    The metrics block lists each metric with its kind + a short
    description so the LLM picks the right aggregation. The
    previous_operation hook (used in Step 6 drill-down) is appended
    when present.
    """
    ds = get_dataset()
    schema = ds.schema

    metric_lines = []
    for name, meta in schema["metrics"].items():
        desc = meta.get("description", "").split(".")[0]
        metric_lines.append(
            f"- {name}  ·  {meta['kind']:8s}  ·  {desc}"
        )
    metrics_block = "\n".join(metric_lines)

    prompt = PLANNER_PROMPT_TEMPLATE.format(
        today=today,
        covered_years=ds.covered_years(),
        channels=ds.dimension_domain("channel"),
        products=ds.dimension_domain("product_line"),
        metrics_block=metrics_block,
    )

    if previous_operation:
        # NB: this block is concatenated AFTER the .format() call
        # above, so braces here are LITERAL, not format escapes -
        # do not double them.
        prompt += (
            "\n\nDRILL-DOWN MODE\n"
            "The user is following up on a previous data turn. "
            "Treat their new question as a PATCH on the previous "
            "Operation:\n"
            "  - Inherit every filter/dimension that the user did "
            "    NOT contradict (year, period, channel, "
            "    product_line, compare_to).\n"
            "  - Apply only the user's new constraints on top.\n"
            "  - Examples:\n"
            "    prev: {metric:'gross_written_premium_eur', "
            "filters:{year:[2024]}}\n"
            "    user: 'now by channel'\n"
            "    -> {metric:'gross_written_premium_eur', "
            "filters:{year:[2024]}, group_by:['channel']}\n"
            "    prev: as above with group_by:['channel']\n"
            "    user: 'only direct'\n"
            "    -> {metric:'gross_written_premium_eur', "
            "filters:{year:[2024], channel:['Direct']}, "
            "group_by:['channel']}\n"
            "If the new question is unrelated (different metric "
            "with no shared dimensions, or a clearly fresh topic), "
            "you may ignore the previous Operation and start fresh.\n"
            "\nPREVIOUS Operation (JSON):\n"
            + json.dumps(previous_operation, indent=2)
            + "\n"
        )

    return prompt


_JSON_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def _parse_operation(raw: str) -> Operation:
    """Extract a JSON Operation from the planner LLM output.

    Tolerates a markdown code-fence (some models add one despite the
    prompt). Anything not parseable raises OperationViolation with
    reason='planner_unparseable' so the data node can surface a
    user-friendly error without crashing the turn.
    """
    text = _JSON_FENCE.sub("", raw.strip()).strip()
    # Greedy object grab in case the model added trailing prose.
    if not text.startswith("{"):
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            text = match.group(0)

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise OperationViolation(
            f"Planner did not emit valid JSON: {exc}",
            reason="planner_unparseable",
            details={"raw_preview": raw[:200]},
        ) from exc

    # Filters/compare_to come back as plain dicts; Pydantic converts
    # them via Filters when validating Operation.
    try:
        return Operation.model_validate(payload)
    except Exception as exc:  # noqa: BLE001
        raise OperationViolation(
            f"Planner emitted an invalid Operation: {exc}",
            reason="planner_invalid",
            details={"payload": payload},
        ) from exc


def plan_query(
    question: str,
    today: str,
    previous_operation: dict | None = None,
) -> Operation:
    """LLM call: question → Operation. Wrapped in its own span."""
    with tracer.start_as_current_span("data.plan") as span:
        span.set_attribute("question.preview", question[:80])
        span.set_attribute(
            "data.plan.drilldown", bool(previous_operation)
        )
        if previous_operation:
            log.info(
                "Drill-down: previous metric=%s aggregation=%s "
                "group_by=%s",
                previous_operation.get("metric"),
                previous_operation.get("aggregation"),
                previous_operation.get("group_by"),
            )
        prompt = _build_planner_prompt(today, previous_operation)
        t0 = time.perf_counter()
        result = get_llm().invoke(
            [
                SystemMessage(content=prompt),
                HumanMessage(content=question),
            ]
        )
        raw = str(result.content)
        elapsed = time.perf_counter() - t0
        span.set_attribute("data.plan.duration_s", round(elapsed, 3))
        span.set_attribute("data.plan.output_chars", len(raw))
        log.info(
            "Planner LLM returned %d chars in %.2fs", len(raw), elapsed
        )

        op = _parse_operation(raw)
        span.set_attribute("data.plan.metric", op.metric)
        span.set_attribute("data.plan.aggregation", op.aggregation)
        log.info(
            "Parsed Operation: metric=%s agg=%s group_by=%s "
            "compare_to=%s",
            op.metric,
            op.aggregation,
            op.group_by,
            "yes" if op.compare_to else "no",
        )
        return op


# ---------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------

def _fmt_value(value: float, unit: str) -> str:
    """Format a single numeric value with its unit nicely for prose."""
    if value is None:
        return "n/a"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return str(value)
    if unit == "EUR":
        return f"€{v:,.0f}"
    if unit == "%":
        return f"{v:.1f}%"
    if unit in ("days", "score"):
        return f"{v:.1f}".rstrip("0").rstrip(".") + f" {unit}"
    if unit:
        return f"{v:,.0f} {unit}"
    return f"{v:,.1f}"


def _pretty_metric(metric: str) -> str:
    """Strip noise suffixes for prose, e.g.
    gross_written_premium_eur -> 'gross written premium'."""
    base = metric
    for suffix in ("_eur", "_pct", "_score", "_count", "_detected"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
    return base.replace("_", " ")


def _scope_phrase(f: Filters) -> str:
    """Compact 'in 2024 · Direct channel · Motor' style descriptor."""
    parts: list[str] = []
    if f.year:
        years = [str(y) for y in f.year]
        parts.append(", ".join(years))
    if f.period:
        parts.append(", ".join(f.period))
    if f.channel:
        parts.append(", ".join(f.channel) + " channel")
    if f.product_line:
        parts.append(", ".join(f.product_line))
    return " · ".join(parts) if parts else "the full dataset"


def _build_narrative(r: ExecutionResult) -> str:
    op = r.operation
    metric_pretty = _pretty_metric(r.metric)
    unit = r.metric_unit
    scope = _scope_phrase(op.filters)

    # Scalar (one row, no group_by) ---------------------------------
    if op.group_by == [] and len(r.result) == 1:
        val = r.result.iloc[0][r.metric]
        line = (
            f"**{metric_pretty.capitalize()}** for {scope}: "
            f"**{_fmt_value(val, unit)}**"
        )
        if r.compare is not None and len(r.compare) == 1:
            cval = r.compare.iloc[0][r.metric]
            cscope = _scope_phrase(op.compare_to)
            try:
                delta = float(val) - float(cval)
                sign = "+" if delta >= 0 else "-"
                line += (
                    f"  \nvs {cscope}: {_fmt_value(cval, unit)} "
                    f"({sign}{_fmt_value(abs(delta), unit)})"
                )
            except (TypeError, ValueError):
                line += f"  \nvs {cscope}: {_fmt_value(cval, unit)}"
        return line

    # Grouped --------------------------------------------------------
    by = ", ".join(op.group_by) if op.group_by else "(no breakdown)"
    return (
        f"**{metric_pretty.capitalize()}** by **{by}** for {scope} "
        f"({r.aggregation} · {len(r.result)} rows):"
    )


def _df_to_md(df) -> str:
    """Minimal pandas DataFrame -> Markdown table (avoids the
    optional `tabulate` dependency that pd.to_markdown pulls in).
    """
    # Round float columns for readable display.
    df = df.copy()
    for col in df.select_dtypes(include="float").columns:
        df[col] = df[col].round(2)
    headers = list(df.columns)
    rows = [
        [
            ("" if v is None else str(v))
            for v in row
        ]
        for row in df.itertuples(index=False, name=None)
    ]
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join(["---"] * len(headers)) + "|"]
    out.extend("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join(out)


def _result_to_markdown(r: ExecutionResult) -> str:
    """Render the result frame as a Markdown table.

    Capped at _MAX_TABLE_ROWS; if a compare frame exists, append a
    second mini-table for it.
    """
    primary = r.result.head(_MAX_TABLE_ROWS)
    out = _df_to_md(primary)
    if r.compare is not None:
        cmp_df = r.compare.head(_MAX_TABLE_ROWS)
        out += "\n\n_Comparison:_\n\n" + _df_to_md(cmp_df)
    if len(r.result) > _MAX_TABLE_ROWS:
        out += (
            f"\n\n_…{len(r.result) - _MAX_TABLE_ROWS} "
            f"more rows truncated._"
        )
    return out


def _refusal_message(exc: OperationViolation, dataset_years: list[int]) -> str:
    """Map an OperationViolation onto a user-facing explanation."""
    if exc.reason == "year_gap":
        requested = exc.details.get("requested", [])
        return (
            f"The dataset doesn't cover {requested}. "
            f"Covered years: {dataset_years}. "
            "Would you like to try one of these instead?"
        )
    if exc.reason == "invalid_aggregation":
        d = exc.details
        return (
            f"Can't apply **{d.get('requested')}** to "
            f"**{d.get('metric')}** (a {d.get('metric_kind')} metric). "
            f"Allowed aggregations for this metric: "
            f"{d.get('allowed')}."
        )
    if exc.reason == "unknown_metric":
        return (
            f"I don't have a metric named **{exc.details.get('metric')}**. "
            f"Known metrics include: {exc.details.get('known', [])[:6]} …"
        )
    if exc.reason == "unknown_dimension_value":
        d = exc.details
        return (
            f"Unknown **{d.get('dimension')}** value(s): "
            f"{d.get('unknown')}. Allowed: {d.get('known')}."
        )
    if exc.reason == "empty_result":
        return (
            "No rows match the filters in your question. "
            "Try widening the date range, channel, or product line."
        )
    if exc.reason in ("planner_unparseable", "planner_invalid"):
        return (
            "I couldn't translate that question into a structured "
            "query. Could you rephrase it? "
            "For example: *\"renewal rate by channel in 2024\"* or "
            "*\"compare GWP 2024 vs 2022\"*."
        )
    # Fallback
    return f"Couldn't run that query: {exc}"


def render(r: ExecutionResult) -> str:
    """Compose the final Markdown answer (narrative + table)."""
    return f"{_build_narrative(r)}\n\n{_result_to_markdown(r)}"


# ---------------------------------------------------------------------
# Node entry point
# ---------------------------------------------------------------------

@dataclass
class DataNodeOutput:
    """What data_node writes back into GraphState."""

    final_answer: str
    operation_json: dict | None
    last_data_operation: dict | None
    csv_sha256: str
    row_count: int


def _diff_against_previous(
    current: dict, previous: dict | None
) -> dict:
    """Annotate which top-level fields the planner inherited vs changed.

    Returns a dict with two lists:
      inherited - fields present in both AND value-equal.
      changed   - fields whose value differs (including new additions).
    Only top-level Operation keys are compared (metric, filters,
    group_by, aggregation, compare_to, sort_by, limit). The UI will
    label fields accordingly in the 'How this was computed' expander.
    """
    if not previous:
        return {"inherited": [], "changed": []}
    keys = (
        "metric", "filters", "group_by", "aggregation",
        "compare_to", "sort_by", "limit",
    )
    inherited, changed = [], []
    for k in keys:
        if current.get(k) == previous.get(k):
            if previous.get(k) not in (None, [], {}):
                inherited.append(k)
        else:
            changed.append(k)
    return {"inherited": inherited, "changed": changed}


def data_node(state: GraphState) -> dict:
    """Run the planner → executor → renderer pipeline for one turn."""
    # GraphState is TypedDict(total=False), so every key is optional
    # from the type checker's perspective. We trust the graph entry
    # point (api.routes.chat) to always populate `question` and fall
    # back to "" defensively if it ever isn't.
    question = state.get("question") or ""
    today = state.get("today") or date.today().isoformat()
    previous_op = state.get("last_data_operation")
    ds = get_dataset()

    with tracer.start_as_current_span("data.node") as span, \
            track_node("data", route="data"):
        annotate_request_span(
            span,
            user_id=state.get("user_id"),
            conversation_id=state.get("conversation_id"),
        )
        span.set_attribute("question.preview", question[:80])
        span.set_attribute("data.csv_sha256", ds.csv_sha256[:12])
        span.set_attribute("data.drilldown", bool(previous_op))

        # Step 1 - plan.
        try:
            op = plan_query(question, today, previous_operation=previous_op)
        except OperationViolation as exc:
            log.warning("Planner refused: %s", exc)
            audit_record(
                state,
                event_type=audit_events.DATA_PLAN,
                payload={
                    "ok": False,
                    "reason": exc.reason,
                    "drilldown": bool(previous_op),
                },
            )
            msg = _refusal_message(exc, ds.covered_years())
            return {
                "final_answer": msg,
                "final_citations": [],
                "validated": True,
                "retry_count": 0,
            }
        audit_record(
            state,
            event_type=audit_events.DATA_PLAN,
            payload={
                "ok": True,
                "operation": op.model_dump(mode="json"),
                "drilldown": bool(previous_op),
            },
        )

        # Step 2 - execute.
        try:
            result = execute(op, dataset=ds)
        except OperationViolation as exc:
            log.warning(
                "Executor refused (reason=%s): %s", exc.reason, exc
            )
            audit_record(
                state,
                event_type=audit_events.DATA_EXECUTE,
                payload={
                    "ok": False,
                    "reason": exc.reason,
                    "operation": op.model_dump(mode="json"),
                    "csv_sha256": ds.csv_sha256,
                },
            )
            msg = _refusal_message(exc, ds.covered_years())
            return {
                "final_answer": msg,
                "final_citations": [],
                "validated": True,
                "retry_count": 0,
                # Preserve the failed Operation so the user can see
                # what the planner intended (UI expander).
                "data_operation": op.model_dump(mode="json"),
            }
        audit_record(
            state,
            event_type=audit_events.DATA_EXECUTE,
            payload={
                "ok": True,
                "row_count": result.row_count,
                "duration_s": round(result.duration_s, 3),
                "csv_sha256": ds.csv_sha256,
                "metric": result.metric,
                "aggregation": result.aggregation,
            },
        )

        # Step 3 - render.
        answer_md = render(result)
        op_json = op.model_dump(mode="json")
        diff = _diff_against_previous(op_json, previous_op)
        # Tag the operation payload with drill-down provenance so the
        # UI can label which fields were inherited from the previous
        # turn and which the user actually changed this turn.
        op_payload = {
            **op_json,
            "_drilldown": bool(previous_op),
            "_inherited": diff["inherited"],
            "_changed": diff["changed"],
        }
        log.info(
            "data_node done: metric=%s rows=%d duration=%.2fs "
            "drilldown=%s inherited=%s changed=%s",
            result.metric,
            result.row_count,
            result.duration_s,
            bool(previous_op),
            diff["inherited"],
            diff["changed"],
        )

        return {
            "final_answer": answer_md,
            "final_citations": [],
            "validated": True,
            "retry_count": 0,
            "data_operation": op_payload,
            "last_data_operation": op_json,
        }
