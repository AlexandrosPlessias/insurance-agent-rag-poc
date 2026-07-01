"""Factories for ChatOllama (qwen2.5) and OllamaEmbeddings (nomic-embed-text)."""
from functools import lru_cache

from langchain_ollama import ChatOllama, OllamaEmbeddings

from app.config import settings


@lru_cache(maxsize=1)
def get_llm() -> ChatOllama:
    return ChatOllama(
        model=settings.llm_model,
        base_url=settings.ollama_host,
        temperature=0,
    )


@lru_cache(maxsize=1)
def get_fast_llm() -> ChatOllama:
    """Phase 11: lighter 3B model for the Planner (low-latency planning)."""
    return ChatOllama(
        model=settings.planner_model,
        base_url=settings.ollama_host,
        temperature=0,
    )


@lru_cache(maxsize=1)
def get_embeddings() -> OllamaEmbeddings:
    return OllamaEmbeddings(
        model=settings.embed_model,
        base_url=settings.ollama_host,
    )
