"""GET /health — liveness and Ollama reachability probe."""
import httpx
from fastapi import APIRouter

from agentic_backend.api.gateway_client import all_service_health
from agentic_backend.api.schemas import HealthResponse
from agentic_backend.config import settings

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    try:
        r = httpx.get(f"{settings.ollama_host}/api/tags", timeout=2.0)
        ollama_ok = r.status_code == 200
    except httpx.HTTPError:
        ollama_ok = False
    return HealthResponse(
        status="ok",
        ollama_reachable=ollama_ok,
        telegram_configured=bool(settings.telegram_bot_token and settings.telegram_chat_id),
        otel_enabled=settings.otel_enabled,
        otel_ui_url=settings.otel_ui_url,
        voice_enabled=settings.voice_enabled,
    )


@router.get("/health/services")
async def services_health() -> list[dict]:
    """Fan out health probes to all downstream pods (Phase 14).

    Returns a list of {name, status, latency_ms} dicts — one per service.
    Used by the React SPA Services panel to show per-pod health without
    requiring direct access to Portainer or the Docker socket.
    """
    return await all_service_health()
