"""FastAPI dependency providers for the graph, stores, and LLM clients."""
from functools import lru_cache

from agentic_backend.config import settings
from agentic_backend.memory.store import MemoryStore


@lru_cache(maxsize=1)
def get_memory_store() -> MemoryStore:
    return MemoryStore(settings.database_url)
