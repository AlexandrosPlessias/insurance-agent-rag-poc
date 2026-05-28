"""Chat endpoints (Phase 2-4).

POST /chat         - invokes the compiled graph; persists user + assistant
                     messages to SQLite.
POST /chat/stream  - NDJSON stream from the manual graph walker; persists
                     the assistant turn after the stream completes.
"""
import json
from typing import Iterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from opentelemetry import trace

from app.api.dependencies import get_memory_store
from app.api.schemas import (
    ChatRequest,
    ChatResponse,
    Citation,
)
from app.graph.builder import get_graph
from app.graph.streaming import stream_graph
from app.memory.store import MemoryStore
from app.observability.logging import get_logger
from app.observability.tracing import annotate_request_span

log = get_logger(__name__)
router = APIRouter()

HISTORY_TURNS = 6          # last N messages from THIS conversation
ACTIVITY_LIMIT = 10        # last N user messages across ALL conversations


def _ensure_conversation(
    store: MemoryStore,
    user_id: str,
    conversation_id: int | None,
) -> int:
    if conversation_id is not None:
        existing = store.get_conversation(conversation_id)
        if existing is not None:
            return conversation_id
    return store.create_conversation(user_id)


def _load_memory(
    store: MemoryStore, user_id: str, conversation_id: int
) -> tuple[list[dict], list[dict]]:
    history = store.get_messages(conversation_id, limit=HISTORY_TURNS)
    activity = store.get_user_activity(user_id, limit=ACTIVITY_LIMIT)
    return history, activity


def _citation_dicts(state: dict) -> list[dict]:
    chunks = state.get("final_citations") or state.get("chunks") or []
    return [
        {
            "source": c.source,
            "page": c.page,
            "content": c.content,
            "download_url": f"/sources/{c.source}",
            "section": getattr(c, "section", "") or "",
            "section_title": getattr(c, "section_title", "") or "",
        }
        for c in chunks
    ]


@router.post("/chat", response_model=ChatResponse)
def chat(
    request: ChatRequest,
    store: MemoryStore = Depends(get_memory_store),
) -> ChatResponse:
    log.info(
        "POST /chat: user=%r conv=%s q=%r",
        request.user_id,
        request.conversation_id,
        request.question[:80],
    )
    conv_id = _ensure_conversation(
        store, request.user_id, request.conversation_id
    )
    annotate_request_span(
        trace.get_current_span(),
        user_id=request.user_id,
        conversation_id=conv_id,
    )
    history, activity = _load_memory(store, request.user_id, conv_id)
    store.add_message(conv_id, "user", request.question)

    state = get_graph().invoke(
        {
            "question": request.question,
            "user_id": request.user_id,
            "conversation_id": conv_id,
            "history": history,
            "user_activity": activity,
        }
    )

    answer = state.get("final_answer", state.get("draft_answer", ""))
    citation_dicts = _citation_dicts(state)
    route = state.get("route", "")

    store.add_message(
        conv_id,
        "assistant",
        answer,
        route=route,
        citations=citation_dicts,
    )

    log.info(
        "POST /chat -> conv=%d route=%s validated=%s cits=%d",
        conv_id,
        route,
        state.get("validated"),
        len(citation_dicts),
    )
    return ChatResponse(
        answer=answer,
        citations=[Citation(**c) for c in citation_dicts],
        reformulated_query=state.get("reformulated_query", ""),
        conversation_id=conv_id,
        route=route,
    )


def _ndjson_persist(
    store: MemoryStore,
    user_id: str,
    conv_id: int,
    question: str,
    history: list[dict],
    activity: list[dict],
) -> Iterator[bytes]:
    """Stream events and persist the assistant turn after they finish."""
    final_chunks: list[str] = []
    citations: list[dict] = []
    route = ""
    store.add_message(conv_id, "user", question)

    # First event carries the conversation_id so the UI can latch on.
    yield (
        json.dumps(
            {"type": "conversation", "conversation_id": conv_id}
        )
        + "\n"
    ).encode("utf-8")

    for event in stream_graph(
        question,
        history=history,
        user_activity=activity,
    ):
        if event.get("type") == "token":
            final_chunks.append(event.get("value", ""))
        elif event.get("type") == "done":
            citations = event.get("citations", []) or []
            route = event.get("route", "") or ""
        yield (json.dumps(event) + "\n").encode("utf-8")

    final_answer = "".join(final_chunks)
    store.add_message(
        conv_id,
        "assistant",
        final_answer,
        route=route,
        citations=citations,
    )
    log.info(
        "POST /chat/stream persisted: conv=%d route=%s cits=%d",
        conv_id,
        route,
        len(citations),
    )


@router.post("/chat/stream")
def chat_stream(
    request: ChatRequest,
    store: MemoryStore = Depends(get_memory_store),
) -> StreamingResponse:
    log.info(
        "POST /chat/stream: user=%r conv=%s q=%r",
        request.user_id,
        request.conversation_id,
        request.question[:80],
    )
    conv_id = _ensure_conversation(
        store, request.user_id, request.conversation_id
    )
    annotate_request_span(
        trace.get_current_span(),
        user_id=request.user_id,
        conversation_id=conv_id,
    )
    history, activity = _load_memory(store, request.user_id, conv_id)
    return StreamingResponse(
        _ndjson_persist(
            store, request.user_id, conv_id, request.question,
            history, activity,
        ),
        media_type="application/x-ndjson",
    )
