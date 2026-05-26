"""Chat endpoints (Phase 2 - LangGraph-backed).

POST /chat         - invokes the compiled graph and returns the final state.
POST /chat/stream  - NDJSON stream from the manual graph walker, which
                     mirrors the compiled graph but emits stage and token
                     events for richer UX.
"""
import json
from typing import Iterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.api.schemas import (
    ChatRequest,
    ChatResponse,
    Citation,
)
from app.graph.builder import get_graph
from app.graph.streaming import stream_graph
from app.observability.logging import get_logger

log = get_logger(__name__)
router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    log.info("POST /chat: %r", request.question[:80])
    state = get_graph().invoke({"question": request.question})
    answer = state.get("final_answer", state.get("draft_answer", ""))
    chunks = state.get("final_citations") or state.get("chunks") or []
    citations = [
        Citation(
            source=c.source,
            page=c.page,
            content=c.content,
            download_url=f"/sources/{c.source}",
        )
        for c in chunks
    ]
    log.info(
        "POST /chat -> route=%s validated=%s retries=%d cits=%d",
        state.get("route"),
        state.get("validated"),
        state.get("retry_count", 0),
        len(citations),
    )
    return ChatResponse(
        answer=answer,
        citations=citations,
        reformulated_query=state.get("reformulated_query", ""),
    )


def _ndjson(question: str) -> Iterator[bytes]:
    for event in stream_graph(question):
        yield (json.dumps(event) + "\n").encode("utf-8")


@router.post("/chat/stream")
def chat_stream(request: ChatRequest) -> StreamingResponse:
    log.info("POST /chat/stream: %r", request.question[:80])
    return StreamingResponse(
        _ndjson(request.question),
        media_type="application/x-ndjson",
    )
