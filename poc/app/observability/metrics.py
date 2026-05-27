"""OpenTelemetry metrics for graph-node steps (Phase 5).

Counter + histogram instruments exposed through the default meter
provider. If OTel isn't configured (or self-disabled because the
backend was unreachable), the SDK gives us a no-op provider, so every
`add` / `record` becomes a cheap no-op.

Aspire's Metrics tab will render:
  rag_poc.node.invocations         counter   {node, route?}
  rag_poc.node.duration            histogram {node, route?}  (seconds)
  rag_poc.validator.outcomes       counter   {result, retry_count}
  rag_poc.rag.chunks_retrieved     histogram {route}

Use `track_node(name)` as a context manager around the body of each
graph node to get both the invocation count and duration in one go.
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
