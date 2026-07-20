"""Minimal FastAPI entrypoint for the agentic-service pod.

Mounts chat, conversations, feedback, and plans routes.
In Phase 14b the api-gateway will forward /chat requests here instead
of executing the LangGraph graph in-process.

Note: the Telegram bot runs only in the api-gateway (main.py) which has
python-telegram-bot installed. The agentic-service does not run it.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agentic_backend.api.routes import chat, conversations, feedback, plans
from agentic_backend.config import settings
from agentic_backend.observability.logging import get_logger
from agentic_backend.observability.tracing import setup_otel

log = get_logger(__name__)

app = FastAPI(title="Agentic Service", version="0.1.0")
setup_otel(app=app, service_suffix="agentic")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat.router)
app.include_router(conversations.router)
app.include_router(feedback.router)
app.include_router(plans.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "agentic-service"}


log.info("Agentic service ready — model=%s", settings.llm_model)
