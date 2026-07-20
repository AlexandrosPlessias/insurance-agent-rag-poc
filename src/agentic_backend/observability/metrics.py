"""OpenTelemetry metrics for graph-node steps.

Counter + histogram instruments exposed through the default meter
provider. If OTel isn't configured (or self-disabled because the
backend was unreachable), the SDK gives us a no-op provider, so every
`add` / `record` becomes a cheap no-op.

Aspire's Metrics tab will render:
  rag_poc.node.invocations         counter   {node, route?}
  rag_poc.node.duration            histogram {node, route?}  (seconds)
  rag_poc.skill.invocations        counter   {skill, route?}
  rag_poc.skill.duration           histogram {skill, route?} (seconds)
  rag_poc.tool.invocations         counter   {skill, tool}
  rag_poc.tool.duration            histogram {skill, tool}   (seconds)
  rag_poc.validator.outcomes       counter   {result, retry_count}
  rag_poc.rag.chunks_retrieved     histogram {route}

Use `track_node(name)` as a context manager around a graph node,
`track_skill(skill)` around a skill execution, and
`track_tool(skill, tool)` around an individual tool call.
"""
import time
from contextlib import contextmanager

from opentelemetry import metrics

_meter = metrics.get_meter("rag_poc")

_node_invocations = _meter.create_counter(
    name="rag_poc.node.invocations",
    description="Number of times each graph node was invoked",
    unit="1",
)

_node_duration = _meter.create_histogram(
    name="rag_poc.node.duration",
    description="Time spent in each graph node",
    unit="s",
)

_validator_outcomes = _meter.create_counter(
    name="rag_poc.validator.outcomes",
    description="Validator pass / fail counts",
    unit="1",
)

_rag_chunks = _meter.create_histogram(
    name="rag_poc.rag.chunks_retrieved",
    description="Number of chunks retrieved per RAG query",
    unit="1",
)

_skill_invocations = _meter.create_counter(
    name="rag_poc.skill.invocations",
    description="Number of times each skill was invoked",
    unit="1",
)

_skill_duration = _meter.create_histogram(
    name="rag_poc.skill.duration",
    description="Time spent executing each skill",
    unit="s",
)

_tool_invocations = _meter.create_counter(
    name="rag_poc.tool.invocations",
    description="Number of times each tool was called within a skill",
    unit="1",
)

_tool_duration = _meter.create_histogram(
    name="rag_poc.tool.duration",
    description="Time spent in each tool call",
    unit="s",
)

# ── Chat / streaming ──────────────────────────────────────────────────────────

_chat_requests = _meter.create_counter(
    name="rag_poc.chat.requests",
    description="Completed chat turns, tagged by route",
    unit="1",
)

_chat_ttft = _meter.create_histogram(
    name="rag_poc.chat.ttft_ms",
    description="Time-to-first-token for streaming chat (ms)",
    unit="ms",
)

_chat_total = _meter.create_histogram(
    name="rag_poc.chat.total_ms",
    description="Total streaming response time from request to last token (ms)",
    unit="ms",
)

# ── Planner ───────────────────────────────────────────────────────────────────

_plan_steps = _meter.create_histogram(
    name="rag_poc.plan.steps",
    description="Number of steps in each generated plan",
    unit="1",
)

# ── Telegram approvals ────────────────────────────────────────────────────────

_telegram_events = _meter.create_counter(
    name="rag_poc.telegram.events",
    description="Telegram approval notifications sent or failed",
    unit="1",
)

_telegram_approvals = _meter.create_counter(
    name="rag_poc.telegram.approvals",
    description="Telegram approval gate outcomes",
    unit="1",
)

# ── Voice ─────────────────────────────────────────────────────────────────────

_voice_requests = _meter.create_counter(
    name="rag_poc.voice.requests",
    description="Voice STT/TTS requests",
    unit="1",
)

_voice_duration = _meter.create_histogram(
    name="rag_poc.voice.duration_ms",
    description="Voice request processing time (ms)",
    unit="ms",
)


@contextmanager
def track_node(node: str, route: str = ""):
    """Bump the invocation counter and time the block as a histogram entry."""
    attrs: dict = {"node": node}
    if route:
        attrs["route"] = route
    _node_invocations.add(1, attrs)
    t0 = time.perf_counter()
    try:
        yield
    finally:
        _node_duration.record(time.perf_counter() - t0, attrs)


def record_validator_outcome(passed: bool, retry_count: int) -> None:
    _validator_outcomes.add(
        1,
        {
            "result": "pass" if passed else "fail",
            "retry_count": str(retry_count),
        },
    )


def record_rag_chunks(count: int, route: str = "rag") -> None:
    _rag_chunks.record(count, {"route": route})


@contextmanager
def track_skill(skill: str, route: str = ""):
    """Bump the skill invocation counter and record duration.

    Wraps the actual skill execution (i.e. the worker_node dispatch) so
    Aspire's Metrics tab shows per-skill invocation counts and latency.
    """
    attrs: dict = {"skill": skill}
    if route:
        attrs["route"] = route
    _skill_invocations.add(1, attrs)
    t0 = time.perf_counter()
    try:
        yield
    finally:
        _skill_duration.record(time.perf_counter() - t0, attrs)


@contextmanager
def track_tool(skill: str, tool: str):
    """Bump the tool invocation counter and record duration.

    Wraps a single tool call within a skill execution (e.g. vector_search,
    kpi_query) so Aspire shows per-tool latency broken down by parent skill.
    """
    attrs = {"skill": skill, "tool": tool}
    _tool_invocations.add(1, attrs)
    t0 = time.perf_counter()
    try:
        yield
    finally:
        _tool_duration.record(time.perf_counter() - t0, attrs)


def record_chat_complete(route: str, ttft_ms: float | None, total_ms: float) -> None:
    """Record a completed streaming chat turn."""
    attrs = {"route": route}
    _chat_requests.add(1, attrs)
    _chat_total.record(total_ms, attrs)
    if ttft_ms is not None:
        _chat_ttft.record(ttft_ms, attrs)


def record_plan_steps(n_steps: int) -> None:
    _plan_steps.record(n_steps, {})


def record_telegram_event(outcome: str) -> None:
    """outcome: 'sent' | 'failed'"""
    _telegram_events.add(1, {"outcome": outcome})


def record_telegram_approval(outcome: str) -> None:
    """outcome: 'approved' | 'rejected' | 'timeout'"""
    _telegram_approvals.add(1, {"outcome": outcome})


def record_voice_request(kind: str, duration_ms: float) -> None:
    """kind: 'transcribe' | 'synthesize'"""
    attrs = {"kind": kind}
    _voice_requests.add(1, attrs)
    _voice_duration.record(duration_ms, attrs)
