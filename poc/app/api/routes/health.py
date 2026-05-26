"""GET /health — liveness and Ollama reachability probe."""
import httpx
from fastapi import APIRouter

from app.api.schemas import HealthResponse
from app.config import settings

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    try:
        r = httpx.get(f"{settings.ollama_host}/api/tags", timeout=2.0)
        ollama_ok = r.status_code == 200
    except httpx.HTTPError:
        ollama_ok = False
    return HealthResponse(status="ok", ollama_reachable=ollama_ok)
