"""POST /chat — runs a user question through the RAG agent.

Phase 1: direct RAG agent call. Phase 2 swaps this for a LangGraph supervisor.
"""
from fastapi import APIRouter

from app.agents.rag_agent import answer_question
from app.api.schemas import ChatRequest, ChatResponse, Citation

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    result = answer_question(request.question)
    return ChatResponse(
        answer=result.answer,
        citations=[Citation(source=c.source, page=c.page) for c in result.citations],
    )
