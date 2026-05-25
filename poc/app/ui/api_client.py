"""Thin httpx client wrapping the FastAPI backend."""
import httpx

from app.config import settings


def post_chat(question: str) -> dict:
    r = httpx.post(
        f"{settings.ui_api_url}/chat",
        json={"question": question},
        timeout=120.0,
    )
    r.raise_for_status()
    return r.json()


def get_health() -> dict:
    r = httpx.get(f"{settings.ui_api_url}/health", timeout=5.0)
    r.raise_for_status()
    return r.json()
