"""Factories for ChatOllama (qwen2.5) and OllamaEmbeddings (nomic-embed-text)."""

from functools import lru_cache

from langchain_ollama import ChatOllama, OllamaEmbeddings

from agentic_backend.config import settings


@lru_cache(maxsize=1)
def get_llm() -> ChatOllama:
    return ChatOllama(
        model=settings.llm_model,
        base_url=settings.ollama_host,
        temperature=0,
        num_ctx=4096,
        num_predict=256,
    )


@lru_cache(maxsize=1)
def get_fast_llm() -> ChatOllama:
    """Lighter 3B model for the Planner — keeps planning latency low."""
    return ChatOllama(
        model=settings.planner_model,
        base_url=settings.ollama_host,
        temperature=0,
        num_ctx=2048,
        num_predict=180,
    )


@lru_cache(maxsize=1)
def get_embeddings() -> OllamaEmbeddings:
    return OllamaEmbeddings(
        model=settings.embed_model,
        base_url=settings.ollama_host,
    )
