"""Smoke import test — catches obvious syntax / import-time errors.

This is intentionally minimal. It exercises module-level execution
(decorators, top-level constant building, prompt loading) without
running anything that hits Ollama / Chroma / the filesystem.

Run with:
cd src && source .venv/bin/activate && pytest tests/unit/test_imports.py
"""

from __future__ import annotations

import importlib

import pytest

_MODULES = [
    # --- Config & API ---
    "agentic_backend.config",
    "agentic_backend.api.main",
    "agentic_backend.api.schemas",
    "agentic_backend.api.dependencies",
    "agentic_backend.api.routes.chat",
    "agentic_backend.api.routes.conversations",
    "agentic_backend.api.routes.feedback",
    "agentic_backend.api.routes.health",
    "agentic_backend.api.routes.ingest",
    "agentic_backend.api.routes.reports",
    "agentic_backend.api.routes.sources",
    # --- Agents ---
    "agentic_backend.agents.assembler_agent",
    "agentic_backend.agents.data_agent",
    "agentic_backend.agents.memory_agent",
    "agentic_backend.agents.planner_agent",
    "agentic_backend.agents.rag_agent",
    "agentic_backend.agents.report_agent",
    "agentic_backend.agents.validator_agent",
    # --- Audit ---
    "agentic_backend.audit",
    "agentic_backend.audit.events",
    "agentic_backend.audit.middleware",
    "agentic_backend.audit.store",
    # --- Data layer ---
    "agentic_backend.data",
    "agentic_backend.data.executor",
    "agentic_backend.data.loader",
    "agentic_backend.data.operations",
    # --- Graph ---
    "agentic_backend.graph.builder",
    "agentic_backend.graph.clarifier",
    "agentic_backend.graph.edges",
    "agentic_backend.graph.orchestrator",
    "agentic_backend.graph.state",
    "agentic_backend.graph.streaming",
    "agentic_backend.graph.supervisor",
    # --- Ingestion ---
    "agentic_backend.ingestion.metadata",
    "agentic_backend.ingestion.pdf_to_md",
    "agentic_backend.ingestion.pipeline",
    "agentic_backend.ingestion.summarizer",
    # --- LLM ---
    "agentic_backend.llm",
    "agentic_backend.llm.ollama_client",
    # --- Memory ---
    "agentic_backend.memory.store",
    "agentic_backend.memory.summarizer",
    # --- Observability ---
    "agentic_backend.observability.logging",
    "agentic_backend.observability.metrics",
    "agentic_backend.observability.tracing",
    # --- RAG ---
    "agentic_backend.rag.chunker",
    "agentic_backend.rag.loader",
    "agentic_backend.rag.retriever",
    "agentic_backend.rag.vectorstore",
    # --- Reporting ---
    "agentic_backend.reporting.charts",
    "agentic_backend.reporting.executive",
    "agentic_backend.reporting.executive.builder",
    "agentic_backend.reporting.executive.collector",
    "agentic_backend.reporting.executive.narrator",
    "agentic_backend.reporting.executive.sections",
    "agentic_backend.reporting.executive.thresholds",
    "agentic_backend.reporting.markdown",
    "agentic_backend.reporting.writers",
    "agentic_backend.reporting.writers.docx_writer",
    "agentic_backend.reporting.writers.markdown_writer",
    "agentic_backend.reporting.writers.pdf_writer",
    # --- Skills ---
    "agentic_backend.skills",
    "agentic_backend.skills.answer_policy_question",
    "agentic_backend.skills.clarify_year",
    "agentic_backend.skills.compute_kpi",
    "agentic_backend.skills.executive_section_summary",
    "agentic_backend.skills.out_of_year_fallback",
    # --- Tools ---
    "agentic_backend.tools",
    "agentic_backend.tools.audit_write",
    "agentic_backend.tools.clarifier_check",
    "agentic_backend.tools.kpi_query",
    "agentic_backend.tools.knowledge_base_lookup",
    "agentic_backend.tools.vector_search",
]


@pytest.mark.parametrize("module_name", _MODULES)
def test_module_importable(module_name: str) -> None:
    importlib.import_module(module_name)
