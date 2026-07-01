"""Compile the LangGraph state machine.

Topology (Phase 11):

    START -> planner -> orchestrator
    orchestrator --(Send "worker" per ready step)--> worker (x N, parallel)
    worker -> orchestrator  (loop until all steps done)
    orchestrator --(all done)--> assembler -> END

The orchestrator node is a no-op relay; all routing logic lives in
`route_orchestrator` (conditional edge). Workers loop back after each
step so dependent steps fire as soon as their prerequisites land in
step_results.

See GRAPH.md at the repo root for the rendered Mermaid version.
"""
from functools import lru_cache

from langgraph.graph import END, START, StateGraph

from app.agents.assembler_agent import assembler_node
from app.agents.planner_agent import planner_node
from app.graph.orchestrator import (
    orchestrator_node,
    route_orchestrator,
    worker_node,
)
from app.graph.state import GraphState
from app.observability.logging import get_logger

log = get_logger(__name__)


@lru_cache(maxsize=1)
def get_graph():
    log.info("Compiling LangGraph state machine (Phase 11) ...")
    builder = StateGraph(GraphState)

    builder.add_node("planner", planner_node)
    builder.add_node("orchestrator", orchestrator_node)
    builder.add_node("worker", worker_node)
    builder.add_node("assembler", assembler_node)

    builder.add_edge(START, "planner")
    builder.add_edge("planner", "orchestrator")

    # route_orchestrator returns list[Send] (fan-out) or "assembler" (string).
    builder.add_conditional_edges(
        "orchestrator",
        route_orchestrator,
        {"assembler": "assembler"},
    )

    # Each worker runs one step then hands control back to the orchestrator
    # so dependent steps are evaluated immediately after a dep completes.
    builder.add_edge("worker", "orchestrator")
    builder.add_edge("assembler", END)

    graph = builder.compile()
    log.info("Graph compiled (Phase 11).")
    return graph
