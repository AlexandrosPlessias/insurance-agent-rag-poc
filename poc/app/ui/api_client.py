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


# --- Feedback (Phase 11) ---


def submit_feedback(
    trace_id: str,
    score: int,
    user_id: str = "default_user",
    plan_id: str = "",
    conversation_id: int | None = None,
    comment: str | None = None,
) -> dict:
    """POST a thumbs-up (+1) or thumbs-down (-1) verdict to /feedback."""
    payload: dict = {
        "trace_id": trace_id,
        "score": score,
        "user_id": user_id,
        "plan_id": plan_id,
    }
    if conversation_id is not None:
        payload["conversation_id"] = conversation_id
    if comment is not None:
        payload["comment"] = comment
    r = httpx.post(f"{_base()}/feedback", json=payload, timeout=5.0)
    r.raise_for_status()
    return r.json()


# --- Ingestion (Phase 6) ---


def upload_document(
    filename: str,
    content: bytes,
    *,
    title: str | None = None,
    description: str | None = None,
    year: int | None = None,
    keywords: str | None = None,
    language: str | None = None,
    document_category: str | None = None,
) -> dict:
    """POST a PDF (+ optional metadata) to /ingest. Returns server JSON."""
    files = {"file": (filename, content, "application/pdf")}
    data: dict = {}
    if title:
        data["title"] = title
    if description:
        data["description"] = description
    if year is not None:
        data["year"] = str(year)
    if keywords:
        data["keywords"] = keywords
    if language:
        data["language"] = language
    if document_category:
        data["document_category"] = document_category
    r = httpx.post(
        f"{_base()}/ingest",
        files=files,
        data=data,
        # Ingestion does a summariser LLM call + embedding pass; allow
        # plenty of time on a cold model.
        timeout=300.0,
    )
    r.raise_for_status()
    return r.json()


# --- Plans / approvals (Phase 12) ---


def approve_plan(plan_id: str, approver_id: str = "ui_user") -> dict:
    r = httpx.post(
        f"{_base()}/plans/{plan_id}/approve",
        json={"approver_id": approver_id, "channel": "ui"},
        timeout=10.0,
    )
    r.raise_for_status()
    return r.json()


def reject_plan(plan_id: str, reason: str = "", approver_id: str = "ui_user") -> dict:
    r = httpx.post(
        f"{_base()}/plans/{plan_id}/reject",
        json={"approver_id": approver_id, "channel": "ui", "reason": reason},
        timeout=10.0,
    )
    r.raise_for_status()
    return r.json()


def get_plan_status(plan_id: str) -> dict:
    r = httpx.get(f"{_base()}/plans/{plan_id}", timeout=5.0)
    r.raise_for_status()
    return r.json()


def stream_plan_resume(plan_id: str) -> Iterator[dict]:
    with httpx.stream(
        "GET",
        f"{_base()}/plans/{plan_id}/resume/stream",
        timeout=180.0,
    ) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if line:
                yield json.loads(line)
