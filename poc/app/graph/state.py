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

    # --- persistent memory (Phase 4) ---
    user_id: str
    conversation_id: int
    history: list[dict]          # last N turns of THIS conversation
    user_activity: list[dict]    # recent msgs ACROSS user's conversations

    # --- supervisor output ---
    route: Literal["rag", "report", "out_of_scope"]

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
