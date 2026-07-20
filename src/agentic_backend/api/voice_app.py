"""Minimal FastAPI entrypoint for the voice-service pod.

Mounts only the /audio/* routes so this container does not need
LangGraph, ChromaDB, or any agentic dependencies.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agentic_backend.api.routes import audio
from agentic_backend.observability.logging import get_logger
from agentic_backend.observability.tracing import setup_otel

log = get_logger(__name__)

app = FastAPI(title="Voice Service", version="0.1.0")
setup_otel(app=app, service_suffix="voice")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(audio.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "voice-service"}


log.info("Voice service ready")
