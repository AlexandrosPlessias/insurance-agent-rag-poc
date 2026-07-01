"""Tool: vector_search — year-scoped ChromaDB retrieval."""
from __future__ import annotations

from app.rag.retriever import RetrievedChunk, retrieve
from app.tools import AgentTool


def _run(
    query: str,
    year_filter: int | None = None,
    k: int = 5,
) -> list[RetrievedChunk]:
    where_filter = {"year": int(year_filter)} if year_filter is not None else None
    return retrieve(query, k=k, where_filter=where_filter)


tool = AgentTool(
    name="vector_search",
    description=(
        "Search the policy knowledge base with semantic similarity. "
        "Optionally filter by policy year."
    ),
    input_fields={
        "query": "search query string",
        "year_filter": "optional int – filter to a specific policy year",
        "k": "number of results to return (default 5)",
    },
    run=_run,
)
