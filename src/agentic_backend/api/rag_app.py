"""Minimal FastAPI entrypoint for the rag-service pod.

Phase 14a: health endpoint only. In Phase 14b, a /rag/search route
will be added so the gateway can forward retrieval requests here.
"""
from fastapi import FastAPI

from agentic_backend.observability.logging import get_logger
from agentic_backend.observability.tracing import setup_otel

log = get_logger(__name__)

app = FastAPI(title="RAG Service", version="0.1.0")
setup_otel(app=app, service_suffix="rag")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "rag-service"}


log.info("RAG service ready")
