"""Chat endpoints.

POST /chat         - invokes the compiled graph; persists user + assistant
                     messages to SQLite.
POST /chat/stream  - NDJSON stream from the manual graph walker; persists
                     the assistant turn after the stream completes.
"""

import json
import time
from typing import Iterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from opentelemetry import context as otel_context
from opentelemetry import trace

from agentic_backend.api.dependencies import get_memory_store
from agentic_backend.api.schemas import (
    ChatRequest,
    ChatResponse,
    Citation,
)
from agentic_backend.config import settings
from agentic_backend.graph.builder import get_graph
from agentic_backend.graph.streaming import stream_graph
from agentic_backend.memory.store import MemoryStore
from agentic_backend.observability.logging import get_logger
from agentic_backend.observability.metrics import record_chat_complete
from agentic_backend.observability.tracing import annotate_request_span

log = get_logger(__name__)
router = APIRouter()

HISTORY_TURNS = 6  # last N messages from THIS conversation
ACTIVITY_LIMIT = 10  # last N user messages across ALL conversations


def _resolve_response_mode(mode: str | None) -> str:
    if mode in {"fast", "accurate"}:
        return mode
    return "fast" if settings.low_latency_mode else "accurate"


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
    # Rolling summarisation: any messages older than the last
    # HISTORY_TURNS get condensed into a single synthetic
    # "system" message so the prompt stays bounded but the model
    # still sees earlier context.
    history = store.get_messages_with_summary(conversation_id, recent_n=HISTORY_TURNS)
    activity = store.get_user_activity(user_id, limit=ACTIVITY_LIMIT)
    return history, activity


def _citation_dicts(state: dict) -> list[dict]:
    """Convert final_citations to plain dicts.

    The agentic orchestrator stores citations as dicts; the legacy path
    stores them as RetrievedChunk dataclasses — handle both.
    """
    chunks = state.get("final_citations") or state.get("chunks") or []
    out = []
    for c in chunks:
        if isinstance(c, dict):
            src = c.get("source", "")
            out.append(
                {
                    "source": src,
                    "content": c.get("content", ""),
                    "download_url": f"/sources/{src}",
                    "section": c.get("section", "") or "",
                    "section_title": c.get("section_title", "") or "",
                    "chunk_index": int(c.get("chunk_index", 0) or 0),
                }
            )
        else:
            src = c.source
            out.append(
                {
                    "source": src,
                    "content": c.content,
                    "download_url": f"/sources/{src}",
                    "section": getattr(c, "section", "") or "",
                    "section_title": getattr(c, "section_title", "") or "",
                    "chunk_index": int(getattr(c, "chunk_index", 0) or 0),
                }
            )
    return out


@router.post("/chat", response_model=ChatResponse)
def chat(
    request: ChatRequest,
    store: MemoryStore = Depends(get_memory_store),
) -> ChatResponse:
    log.info(
        "POST /chat: user=%r conv=%s mode=%s q=%r",
        request.user_id,
        request.conversation_id,
        _resolve_response_mode(request.response_mode),
        request.question[:80],
    )
    conv_id = _ensure_conversation(store, request.user_id, request.conversation_id)
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
            "response_mode": _resolve_response_mode(request.response_mode),
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
    plan_id = (state.get("plan") or {}).get("plan_id", "")

    return ChatResponse(
        answer=answer,
        citations=[Citation(**c) for c in citation_dicts],
        reformulated_query=state.get("reformulated_query", ""),
        conversation_id=conv_id,
        route=route,
        plan_id=plan_id,
        intent=str(state.get("planner_intent", "")),
        effective_response_mode=(
            str(state.get("response_mode"))
            if state.get("response_mode") in {"fast", "accurate"}
            else None
        ),
    )


def _ndjson_persist(
    store: MemoryStore,
    user_id: str,
    conv_id: int,
    question: str,
    response_mode: str,
    history: list[dict],
    activity: list[dict],
    last_data_operation: dict | None = None,
    otel_ctx: object | None = None,
) -> Iterator[bytes]:
    """Stream events and persist the assistant turn after they finish."""
    # Attach the caller's OTel context so child spans created inside the
    # threadpool generator are children of the HTTP request span.
    token = otel_context.attach(otel_ctx) if otel_ctx is not None else None
    final_chunks: list[str] = []
    citations: list[dict] = []
    route = ""
    store.add_message(conv_id, "user", question)
    t_start = time.perf_counter()
    t_first_token: float | None = None

    # First event carries the conversation_id so the UI can latch on.
    yield (json.dumps({"type": "conversation", "conversation_id": conv_id}) + "\n").encode("utf-8")

    for event in stream_graph(
        question,
        history=history,
        user_activity=activity,
        user_id=user_id,
        conversation_id=conv_id,
        last_data_operation=last_data_operation,
        response_mode=response_mode,
    ):
        if event.get("type") == "token":
            final_chunks.append(event.get("value", ""))
            if t_first_token is None:
                t_first_token = time.perf_counter()
        elif event.get("type") == "done":
            citations = event.get("citations", []) or []
            route = event.get("route", "") or ""
        yield (json.dumps(event) + "\n").encode("utf-8")

    final_answer = "".join(final_chunks)
    t_end = time.perf_counter()
    record_chat_complete(
        route=route,
        ttft_ms=(t_first_token - t_start) * 1000 if t_first_token else None,
        total_ms=(t_end - t_start) * 1000,
    )
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
    if token is not None:
        try:
            otel_context.detach(token)
        except ValueError:
            # Token was created in a different threadpool thread context;
            # the thread's contextvars copy is discarded on reclaim anyway.
            pass


@router.post("/chat/stream")
def chat_stream(
    request: ChatRequest,
    store: MemoryStore = Depends(get_memory_store),
) -> StreamingResponse:
    log.info(
        "POST /chat/stream: user=%r conv=%s mode=%s q=%r",
        request.user_id,
        request.conversation_id,
        _resolve_response_mode(request.response_mode),
        request.question[:80],
    )
    conv_id = _ensure_conversation(store, request.user_id, request.conversation_id)
    annotate_request_span(
        trace.get_current_span(),
        user_id=request.user_id,
        conversation_id=conv_id,
    )
    history, activity = _load_memory(store, request.user_id, conv_id)
    return StreamingResponse(
        _ndjson_persist(
            store,
            request.user_id,
            conv_id,
            request.question,
            _resolve_response_mode(request.response_mode),
            history,
            activity,
            last_data_operation=request.last_data_operation,
            otel_ctx=otel_context.get_current(),
        ),
        media_type="application/x-ndjson",
    )
