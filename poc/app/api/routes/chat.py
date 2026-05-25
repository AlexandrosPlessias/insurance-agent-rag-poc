"""POST /chat - runs a user question through the RAG agent.

Phase 1: direct RAG agent call. Phase 2 swaps this for a LangGraph
supervisor.
"""
from fastapi import APIRouter

from app.agents.rag_agent import answer_question
from app.api.schemas import ChatRequest, ChatResponse, Citation
from app.observability.logging import get_logger

log = get_logger(__name__)
router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    log.info("POST /chat: %r", request.question[:80])
    result = answer_question(request.question)
    log.info(
        "POST /chat -> %d citations, %d-char answer",
        len(result.citations),
        len(result.answer),
    )
    citations = [
        Citation(source=c.source, page=c.page) for c in result.citations
    ]
    return ChatResponse(answer=result.answer, citations=citations)
