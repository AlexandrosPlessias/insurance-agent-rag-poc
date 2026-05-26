"""Thin httpx client wrapping the FastAPI backend."""
import json
from typing import Iterator

import httpx

from app.config import settings


def _base() -> str:
    return settings.ui_api_url


def post_chat(
    question: str,
    user_id: str = "default_user",
    conversation_id: int | None = None,
) -> dict:
    payload = {"question": question, "user_id": user_id}
    if conversation_id is not None:
        payload["conversation_id"] = conversation_id
    r = httpx.post(
        f"{_base()}/chat", json=payload, timeout=180.0,
    )
    r.raise_for_status()
    return r.json()


def stream_chat(
    question: str,
    user_id: str = "default_user",
    conversation_id: int | None = None,
) -> Iterator[dict]:
    payload = {"question": question, "user_id": user_id}
    if conversation_id is not None:
        payload["conversation_id"] = conversation_id
    with httpx.stream(
        "POST",
        f"{_base()}/chat/stream",
        json=payload,
        timeout=180.0,
    ) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if line:
                yield json.loads(line)


def get_health() -> dict:
    r = httpx.get(f"{_base()}/health", timeout=5.0)
    r.raise_for_status()
    return r.json()


def source_url(filename: str) -> str:
    return f"{_base()}/sources/{filename}"


# --- Conversations (Phase 4) ---


def list_conversations(user_id: str) -> list[dict]:
    r = httpx.get(
        f"{_base()}/conversations",
        params={"user_id": user_id},
        timeout=5.0,
    )
    r.raise_for_status()
    return r.json()


def create_conversation(
    user_id: str, title: str | None = None
) -> dict:
    payload: dict = {"user_id": user_id}
    if title is not None:
        payload["title"] = title
    r = httpx.post(
        f"{_base()}/conversations", json=payload, timeout=5.0
    )
    r.raise_for_status()
    return r.json()


def get_messages(conversation_id: int) -> list[dict]:
    r = httpx.get(
        f"{_base()}/conversations/{conversation_id}/messages",
        timeout=10.0,
    )
    r.raise_for_status()
    return r.json()
