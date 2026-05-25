"""Thin httpx client wrapping the FastAPI backend."""
import json
from typing import Iterator

import httpx

from app.config import settings


def post_chat(question: str) -> dict:
    """Non-streaming chat call - returns full answer at once."""
    r = httpx.post(
        f"{settings.ui_api_url}/chat",
        json={"question": question},
        timeout=180.0,
    )
    r.raise_for_status()
    return r.json()


def stream_chat(question: str) -> Iterator[dict]:
    """Streaming chat call - yields NDJSON event dicts.

    Event types: meta, token, done, error.
    """
    with httpx.stream(
        "POST",
        f"{settings.ui_api_url}/chat/stream",
        json={"question": question},
        timeout=180.0,
    ) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if line:
                yield json.loads(line)


def get_health() -> dict:
    r = httpx.get(f"{settings.ui_api_url}/health", timeout=5.0)
    r.raise_for_status()
    return r.json()


def source_url(filename: str) -> str:
    return f"{settings.ui_api_url}/sources/{filename}"
