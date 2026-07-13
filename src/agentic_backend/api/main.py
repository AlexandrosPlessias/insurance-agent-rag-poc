"""FastAPI application factory and uvicorn entrypoint."""
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from agentic_backend.api.routes import (
    admin,
    audio,
    chat,
    conversations,
    feedback,
    health,
    ingest,
    plans,
    reports,
    sources,
)
from agentic_backend.config import settings
from agentic_backend.observability.logging import get_logger
from agentic_backend.observability.tracing import setup_otel

log = get_logger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    bot_task: asyncio.Task | None = None
    token = getattr(settings, "telegram_bot_token", "") or ""
    if token:
        from agentic_backend.approvals.telegram_bot import run as _run_bot
        bot_task = asyncio.create_task(_run_bot(token), name="telegram-bot")
        log.info("Telegram bot started as background task")

    yield

    if bot_task:
        bot_task.cancel()
        try:
            await bot_task
        except asyncio.CancelledError:
            pass
        log.info("Telegram bot stopped")


app = FastAPI(title="Insurance Assistant PoC", version="0.5.0", lifespan=_lifespan)

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
app.include_router(audio.router)
app.include_router(chat.router)
app.include_router(conversations.router)
app.include_router(ingest.router)
app.include_router(sources.router)
app.include_router(reports.router)
app.include_router(feedback.router)
app.include_router(plans.router)
app.include_router(admin.router)

log.info(
    "FastAPI ready - model=%s embed=%s chroma=%s sqlite=%s otel=%s",
    settings.llm_model,
    settings.embed_model,
    settings.chroma_persist_dir,
    settings.sqlite_path,
    settings.otel_enabled,
)

_tg_status = (
    "configured — bot embedded in FastAPI"
    if settings.telegram_bot_token
    else "NOT configured (set TELEGRAM_BOT_TOKEN to enable)"
)
log.info("HITL approval channel: Telegram %s", _tg_status)

# Serve React SPA from frontend/dist if it has been built (vite build).
# The wildcard mount must come last — after all API routers.
_frontend_dist = Path(__file__).parent.parent.parent / "frontend" / "dist"
if _frontend_dist.exists():
    app.mount("/", StaticFiles(directory=_frontend_dist, html=True), name="frontend")
    log.info("Serving React SPA from %s", _frontend_dist)
