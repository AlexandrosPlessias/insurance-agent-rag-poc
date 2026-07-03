"""FastAPI application factory and uvicorn entrypoint."""
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import (
    chat,
    conversations,
    feedback,
    health,
    ingest,
    plans,
    reports,
    sources,
)
from app.config import settings
from app.observability.logging import get_logger
from app.observability.tracing import setup_otel

log = get_logger(__name__)

app = FastAPI(title="Insurance Assistant PoC", version="0.5.0")

# Initialise OTel (no-op if OTEL_ENABLED=false). Must run before the
# routers see traffic so FastAPIInstrumentor can wrap the app.
setup_otel(app=app, service_suffix="api")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(chat.router)
app.include_router(conversations.router)
app.include_router(ingest.router)
app.include_router(sources.router)
app.include_router(reports.router)
app.include_router(feedback.router)
app.include_router(plans.router)

log.info(
    "FastAPI ready - model=%s embed=%s chroma=%s sqlite=%s otel=%s",
    settings.llm_model,
    settings.embed_model,
    settings.chroma_persist_dir,
    settings.sqlite_path,
    settings.otel_enabled,
)

_tg_status = "configured" if settings.telegram_bot_token else "NOT configured — run scripts/run_telegram_bot.py"
log.info("Phase 12 approval channel: Telegram %s", _tg_status)

# Serve React SPA from frontend/dist if it has been built (vite build).
# The wildcard mount must come last — after all API routers.
_frontend_dist = Path(__file__).parent.parent.parent / "frontend" / "dist"
if _frontend_dist.exists():
    app.mount("/", StaticFiles(directory=_frontend_dist, html=True), name="frontend")
    log.info("Serving React SPA from %s", _frontend_dist)
