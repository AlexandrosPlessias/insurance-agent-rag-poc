"""GraphState TypedDict shared across all LangGraph nodes."""
from typing import Literal, TypedDict

from app.rag.retriever import RetrievedChunk


class ValidationResult(TypedDict, total=False):
    grounded: bool
    citations_ok: bool
    critique: str


class GraphState(TypedDict, total=False):
    # --- input ---
    question: str

    # --- supervisor output ---
    route: Literal["rag", "out_of_scope"]

    # --- rag node output ---
    reformulated_query: str
    chunks: list[RetrievedChunk]
    draft_answer: str

    # --- validator output ---
    validation: ValidationResult
    retry_count: int
    last_critique: str

    # --- terminal ---
    final_answer: str
    final_citations: list[RetrievedChunk]
    validated: bool
