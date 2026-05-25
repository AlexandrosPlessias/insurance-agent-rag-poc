"""Chat endpoints.

POST /chat         - non-streaming, returns full answer + citations.
POST /chat/stream  - NDJSON stream of {meta, token..., done} events.

Phase 1: direct RAG agent. Phase 2 swaps it for a LangGraph supervisor.
"""
import json
from typing import Iterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.agents.rag_agent import answer_question, answer_question_stream
from app.api.schemas import (
    ChatRequest,
    ChatResponse,
    Citation,
)
from app.observability.logging import get_logger

log = get_logger(__name__)
router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    log.info("POST /chat: %r", request.question[:80])
    result = answer_question(request.question)
    citations = [
        Citation(
            source=c.source,
            page=c.page,
            content=c.content,
            download_url=f"/sources/{c.source}",
        )
        for c in result.citations
    ]
    log.info(
        "POST /chat -> %d citations, %d-char answer",
        len(citations),
        len(result.answer),
    )
    return ChatResponse(
        answer=result.answer,
        citations=citations,
        reformulated_query=result.reformulated_query,
    )


def _ndjson(question: str) -> Iterator[bytes]:
    for event in answer_question_stream(question):
        yield (json.dumps(event) + "\n").encode("utf-8")


@router.post("/chat/stream")
def chat_stream(request: ChatRequest) -> StreamingResponse:
    log.info("POST /chat/stream: %r", request.question[:80])
    return StreamingResponse(
        _ndjson(request.question),
        media_type="application/x-ndjson",
    )
