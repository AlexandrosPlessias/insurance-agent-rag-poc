"""Pydantic request and response models for the API."""
from pydantic import BaseModel, Field


# --- Chat ---


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1)
    user_id: str = "default_user"
    conversation_id: int | None = None


class Citation(BaseModel):
    source: str
    # `page` is a legacy field; newer chunks don't carry a page number
    # (page tracking was removed to keep cross-page sentences intact).
    # UI / smoke test hide it when 0.
    page: int = 0
    content: str = ""
    download_url: str = ""
    section: str = ""
    section_title: str = ""


class ChatResponse(BaseModel):
    answer: str
    citations: list[Citation]
    reformulated_query: str = ""
    conversation_id: int | None = None
    route: str = ""


class HealthResponse(BaseModel):
    status: str
    ollama_reachable: bool


# --- Conversations (Phase 4) ---


class ConversationCreate(BaseModel):
    user_id: str = "default_user"
    title: str | None = None


class Conversation(BaseModel):
    id: int
    user_id: str
    title: str | None = None
    created_at: str


class Message(BaseModel):
    id: int
    conversation_id: int
    role: str
    content: str
    route: str | None = None
    citations: list[Citation] = []
    created_at: str
