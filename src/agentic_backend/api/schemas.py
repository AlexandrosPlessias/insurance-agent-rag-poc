"""Pydantic request and response models for the API."""

from typing import Literal

from pydantic import BaseModel, Field

# --- Chat ---


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1)
    user_id: str = "default_user"
    conversation_id: int | None = None
    last_data_operation: dict | None = None
    response_mode: Literal["fast", "accurate"] | None = None


class Citation(BaseModel):
    source: str
    content: str = ""
    download_url: str = ""
    section: str = ""
    section_title: str = ""
    chunk_index: int = 0


class ChatResponse(BaseModel):
    answer: str
    citations: list[Citation]
    reformulated_query: str = ""
    conversation_id: int | None = None
    route: str = ""
    plan_id: str = ""  # for client-side feedback submission
    intent: str = ""
    effective_response_mode: Literal["fast", "accurate"] | None = None


class HealthResponse(BaseModel):
    status: str
    ollama_reachable: bool
    telegram_configured: bool
    otel_enabled: bool
    otel_ui_url: str
    voice_enabled: bool


# --- Conversations ---


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


# --- Feedback ---


class FeedbackRequest(BaseModel):
    trace_id: str
    plan_id: str = ""
    user_id: str = "default_user"
    score: int = Field(..., ge=-1, le=1)  # +1 thumbs-up, -1 thumbs-down
    comment: str | None = None
    conversation_id: int | None = None


class FeedbackResponse(BaseModel):
    ok: bool
    row_id: int
