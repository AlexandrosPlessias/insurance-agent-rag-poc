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
    # --- Config & API ---
    "app.config",
    "app.api.main",
    "app.api.schemas",
    "app.api.dependencies",
    "app.api.routes.chat",
    "app.api.routes.conversations",
    "app.api.routes.feedback",
    "app.api.routes.health",
    "app.api.routes.ingest",
    "app.api.routes.reports",
    "app.api.routes.sources",
    # --- Agents ---
    "app.agents.assembler_agent",
    "app.agents.data_agent",
    "app.agents.memory_agent",
    "app.agents.planner_agent",
    "app.agents.rag_agent",
    "app.agents.report_agent",
    "app.agents.validator_agent",
    # --- Audit ---
    "app.audit",
    "app.audit.events",
    "app.audit.middleware",
    "app.audit.store",
    # --- Data layer (Phase 8) ---
    "app.data",
    "app.data.executor",
    "app.data.loader",
    "app.data.operations",
    # --- Graph ---
    "app.graph.builder",
    "app.graph.clarifier",
    "app.graph.edges",
    "app.graph.orchestrator",
    "app.graph.state",
    "app.graph.streaming",
    "app.graph.supervisor",
    # --- Ingestion ---
    "app.ingestion.metadata",
    "app.ingestion.pdf_to_md",
    "app.ingestion.pipeline",
    "app.ingestion.summarizer",
    # --- LLM ---
    "app.llm",
    "app.llm.ollama_client",
    # --- Memory ---
    "app.memory.store",
    "app.memory.summarizer",
    # --- Observability ---
    "app.observability.logging",
    "app.observability.metrics",
    "app.observability.tracing",
    # --- RAG ---
    "app.rag.chunker",
    "app.rag.loader",
    "app.rag.retriever",
    "app.rag.vectorstore",
    # --- Reporting ---
    "app.reporting.charts",
    "app.reporting.executive",
    "app.reporting.executive.builder",
    "app.reporting.executive.collector",
    "app.reporting.executive.narrator",
    "app.reporting.executive.sections",
    "app.reporting.executive.thresholds",
    "app.reporting.markdown",
    "app.reporting.writers",
    "app.reporting.writers.docx_writer",
    "app.reporting.writers.markdown_writer",
    "app.reporting.writers.pdf_writer",
    # --- Skills (Phase 11) ---
    "app.skills",
    "app.skills.answer_policy_question",
    "app.skills.clarify_year",
    "app.skills.compute_kpi",
    "app.skills.executive_section_summary",
    "app.skills.out_of_year_fallback",
    # --- Tools (Phase 11) ---
    "app.tools",
    "app.tools.audit_write",
    "app.tools.clarifier_check",
    "app.tools.kpi_query",
    "app.tools.knowledge_base_lookup",
    "app.tools.vector_search",
]


@pytest.mark.parametrize("module_name", _MODULES)
def test_module_importable(module_name: str) -> None:
    importlib.import_module(module_name)
