"""Compile the LangGraph state machine.

Topology (Phase 8):

    START -> supervisor
    supervisor --(out_of_scope)--------> decline    --> END
    supervisor --(report)--------------> report     --> END
    supervisor --(needs_clarification)-> clarifier  --> END
    supervisor --(out_of_year)---------> fallback   --> END
    supervisor --(data)----------------> data       --> END
    supervisor --(rag)----------------->  rag --> validator
    validator  --(retry)---------------> rag (max 1 retry)
    validator  --(end)-----------------> END

See GRAPH.md at the repo root for the rendered Mermaid version.
"""
from functools import lru_cache

from langgraph.graph import END, START, StateGraph

from app.agents.data_agent import data_node
from app.agents.rag_agent import rag_node
from app.agents.report_agent import report_node
from app.agents.validator_agent import validator_node
from app.graph.clarifier import clarifier_node
from app.graph.edges import route_from_supervisor, route_from_validator
from app.graph.state import GraphState
from app.graph.supervisor import (
    decline_node,
    fallback_node,
    supervisor_node,
)
from app.observability.logging import get_logger

log = get_logger(__name__)


@lru_cache(maxsize=1)
def get_graph():
    log.info("Compiling LangGraph state machine ...")
    builder = StateGraph(GraphState)

    builder.add_node("supervisor", supervisor_node)
    builder.add_node("decline", decline_node)
    builder.add_node("clarifier", clarifier_node)
    builder.add_node("fallback", fallback_node)
    builder.add_node("rag", rag_node)
    builder.add_node("validator", validator_node)
    builder.add_node("report", report_node)
    builder.add_node("data", data_node)

    builder.add_edge(START, "supervisor")
    builder.add_conditional_edges(
        "supervisor",
        route_from_supervisor,
        {
            "rag": "rag",
            "report": "report",
            "data": "data",
            "out_of_scope": "decline",
            "needs_clarification": "clarifier",
            "out_of_year": "fallback",
        },
    )
    builder.add_edge("decline", END)
    builder.add_edge("clarifier", END)
    builder.add_edge("fallback", END)
    builder.add_edge("report", END)
    builder.add_edge("data", END)
    builder.add_edge("rag", "validator")
    builder.add_conditional_edges(
        "validator",
        route_from_validator,
        {"retry": "rag", "end": END},
    )

    graph = builder.compile()
    log.info("Graph compiled.")
    return graph
