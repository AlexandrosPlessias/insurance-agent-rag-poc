"""HTTP client for inter-service calls in the Docker Compose stack (Phase 14).

In the monolith (local dev without Docker) every service runs in-process,
so these helpers are not invoked — routes import the local implementations
directly.  When AGENTIC_SERVICE_URL / RAG_SERVICE_URL / VOICE_SERVICE_URL /
INGESTION_SERVICE_URL point at separate containers, the api-gateway uses
these helpers to fan requests out.

Streaming note: stream_post() uses httpx streaming so SSE chunks from
/chat/stream are forwarded token-by-token without buffering.
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx

from agentic_backend.config import settings
from agentic_backend.observability.logging import get_logger

log = get_logger(__name__)

_TIMEOUT = httpx.Timeout(connect=5.0, read=300.0, write=30.0, pool=5.0)


async def post(url: str, payload: dict[str, Any]) -> httpx.Response:
    """Single-shot JSON POST; raises on HTTP error."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()
        return response


async def stream_post(url: str, payload: dict[str, Any]) -> AsyncIterator[bytes]:
    """Streaming POST — yields raw bytes as they arrive (for SSE fan-through)."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        async with client.stream("POST", url, json=payload) as response:
            response.raise_for_status()
            async for chunk in response.aiter_bytes():
                if chunk:
                    yield chunk


async def service_health(name: str, url: str) -> dict[str, Any]:
    """Probe a downstream /health endpoint; returns a status dict."""
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(3.0)) as client:
            r = await client.get(f"{url}/health")
            latency_ms = int(r.elapsed.total_seconds() * 1000)
            is_ok = r.status_code == 200
            return {"name": name, "status": "ok" if is_ok else "degraded", "latency_ms": latency_ms}
    except Exception as exc:
        log.warning("Health probe failed for %s (%s): %s", name, url, exc)
        return {"name": name, "status": "down", "latency_ms": -1}


async def all_service_health() -> list[dict[str, Any]]:
    """Fan out health probes to all downstream services concurrently."""
    import asyncio

    targets = [
        ("agentic-service", settings.agentic_service_url),
        ("rag-service", settings.rag_service_url),
        ("voice-service", settings.voice_service_url),
        ("ingestion-service", settings.ingestion_service_url),
    ]
    return list(await asyncio.gather(*[service_health(n, u) for n, u in targets]))
