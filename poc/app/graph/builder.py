"""Compile the LangGraph state machine.

Topology:

    START
      |
      v
    supervisor ---(out_of_scope)---> decline ----> END
      |
      v (rag)
    rag --------------------------+
      |                           |
      v                           |
    validator --(retry)-----------+
      |
      v (end)
     END
"""
from functools import lru_cache

from langgraph.graph import END, START, StateGraph

from app.agents.rag_agent import rag_node
from app.agents.validator_agent import validator_node
from app.graph.edges import route_from_supervisor, route_from_validator
from app.graph.state import GraphState
from app.graph.supervisor import decline_node, supervisor_node
from app.observability.logging import get_logger

log = get_logger(__name__)


@lru_cache(maxsize=1)
def get_graph():
    log.info("Compiling LangGraph state machine ...")
    builder = StateGraph(GraphState)

    builder.add_node("supervisor", supervisor_node)
    builder.add_node("decline", decline_node)
    builder.add_node("rag", rag_node)
    builder.add_node("validator", validator_node)

    builder.add_edge(START, "supervisor")
    builder.add_conditional_edges(
        "supervisor",
        route_from_supervisor,
        {"rag": "rag", "out_of_scope": "decline"},
    )
    builder.add_edge("decline", END)
    builder.add_edge("rag", "validator")
    builder.add_conditional_edges(
        "validator",
        route_from_validator,
        {"retry": "rag", "end": END},
    )

    graph = builder.compile()
    log.info("Graph compiled.")
    return graph
