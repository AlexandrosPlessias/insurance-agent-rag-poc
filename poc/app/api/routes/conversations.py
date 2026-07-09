"""GET/POST /conversations and GET /conversations/{id}/messages.

Phase 4: lets the UI list, create, and replay conversations.
"""
from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import get_memory_store
from app.api.schemas import (
    Citation,
    Conversation,
    ConversationCreate,
    Message,
)
from app.memory.store import MemoryStore
from app.observability.logging import get_logger

log = get_logger(__name__)
router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("", response_model=list[Conversation])
def list_conversations(
    user_id: str = "default_user",
    store: MemoryStore = Depends(get_memory_store),
) -> list[Conversation]:
    rows = store.list_conversations(user_id)
    return [Conversation(**r) for r in rows]


@router.post("", response_model=Conversation)
def create_conversation(
    payload: ConversationCreate,
    store: MemoryStore = Depends(get_memory_store),
) -> Conversation:
    conv_id = store.create_conversation(payload.user_id, payload.title)
    row = store.get_conversation(conv_id)
    if row is None:
        raise HTTPException(500, "Failed to create conversation")
    return Conversation(**row)


@router.delete("/{conversation_id}", status_code=204)
def delete_conversation(
    conversation_id: int,
    store: MemoryStore = Depends(get_memory_store),
) -> None:
    store.delete_conversation(conversation_id)


@router.get("/{conversation_id}/messages", response_model=list[Message])
def get_messages(
    conversation_id: int,
    store: MemoryStore = Depends(get_memory_store),
) -> list[Message]:
    msgs = store.get_messages(conversation_id)
    out: list[Message] = []
    for m in msgs:
        out.append(
            Message(
                id=m["id"],
                conversation_id=m["conversation_id"],
                role=m["role"],
                content=m["content"],
                route=m.get("route"),
                citations=[
                    Citation(**c) for c in (m.get("citations") or [])
                ],
                created_at=str(m["created_at"]),
            )
        )
    return out
