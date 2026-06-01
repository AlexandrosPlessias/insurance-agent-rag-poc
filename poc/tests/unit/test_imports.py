"""Smoke import test - catches obvious syntax / import-time errors.

This is intentionally minimal. It exercises module-level execution
(decorators, top-level constant building, prompt loading) without
running anything that hits Ollama / Chroma / the filesystem.

Run with:
cd poc && source .venv/bin/activate && pytest tests/unit/test_imports.py
"""

from __future__ import annotations

import importlib

import pytest

_MODULES = [
    "app.config",
    "app.api.main",
    "app.api.schemas",
    "app.api.dependencies",
    "app.api.routes.chat",
    "app.api.routes.conversations",
    "app.api.routes.health",
    "app.api.routes.ingest",
    "app.api.routes.sources",
    "app.agents.rag_agent",
    "app.agents.report_agent",
    "app.agents.validator_agent",
    "app.agents.memory_agent",
    "app.audit",
    "app.audit.events",
    "app.audit.middleware",
    "app.audit.store",
    "app.graph.builder",
    "app.graph.clarifier",
    "app.graph.state",
    "app.graph.streaming",
    "app.graph.supervisor",
    "app.graph.edges",
    "app.rag.chunker",
    "app.rag.loader",
    "app.rag.retriever",
    "app.rag.vectorstore",
    "app.memory.store",
    "app.ingestion.pipeline",
    "app.ingestion.metadata",
    "app.ingestion.pdf_to_md",
    "app.ingestion.summarizer",
    "app.reporting.charts",
    "app.reporting.markdown",
    "app.llm",
    "app.llm.ollama_client",
    "app.observability.tracing",
    "app.observability.metrics",
    "app.observability.logging",
]


@pytest.mark.parametrize("module_name", _MODULES)
def test_module_importable(module_name: str) -> None:
    importlib.import_module(module_name)
