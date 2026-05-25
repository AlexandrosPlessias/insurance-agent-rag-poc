"""Pydantic request and response models for the API."""
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1)


class Citation(BaseModel):
    source: str
    page: int
    content: str = ""
    download_url: str = ""


class ChatResponse(BaseModel):
    answer: str
    citations: list[Citation]
    reformulated_query: str = ""


class HealthResponse(BaseModel):
    status: str
    ollama_reachable: bool
