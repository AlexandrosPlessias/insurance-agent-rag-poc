"""FastAPI application factory and uvicorn entrypoint."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import chat, health
from app.config import settings
from app.observability.logging import get_logger

log = get_logger(__name__)

app = FastAPI(title="Insurance Assistant PoC", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(chat.router)

log.info(
    "FastAPI ready — model=%s embed=%s chroma=%s",
    settings.llm_model,
    settings.embed_model,
    settings.chroma_persist_dir,
)
