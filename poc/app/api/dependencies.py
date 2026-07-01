"""FastAPI dependency providers for the graph, stores, and LLM clients."""
from functools import lru_cache

from app.config import settings
from app.memory.store import MemoryStore


@lru_cache(maxsize=1)
def get_memory_store() -> MemoryStore:
    return MemoryStore(settings.sqlite_path)
