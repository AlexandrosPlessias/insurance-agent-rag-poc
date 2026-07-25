"""Integration test fixtures — requires a running Docker stack (ChromaDB + Ollama).

All tests call the agentic-service HTTP API (POST /chat) rather than
invoking the graph directly. This exercises the full HTTP stack and makes
the `route` and `intent` fields in the response available for assertion.
"""

from __future__ import annotations

from typing import Callable

import httpx
import pytest

from agentic_backend.config import settings
from agentic_backend.rag.vectorstore import get_chunk_count, reset_collection

SMOKE_USER = "smoke_test_user"
AGENTIC_URL = "http://localhost:8002"


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--skip-ingest",
        action="store_true",
        default=False,
        help="Skip PDF reset and ingestion — use existing ChromaDB data.",
    )


@pytest.fixture(scope="session")
def skip_ingest(request: pytest.FixtureRequest) -> bool:
    return bool(request.config.getoption("--skip-ingest"))


@pytest.fixture(scope="session", autouse=True)
def chromadb_setup(skip_ingest: bool) -> None:
    """Ensure ChromaDB is populated before any integration test runs.

    With --skip-ingest: verifies ChromaDB is non-empty (ingestion-service must
    have already run). Without the flag: resets the collection and ingests the
    2024 seed PDF through the full pipeline.
    """
    if skip_ingest:
        chunk_count = get_chunk_count()
        if chunk_count == 0:
            pytest.exit(
                "ChromaDB is empty and --skip-ingest was set. "
                "Run ingestion first: "
                "docker compose exec ingestion-service python scripts/ingest_pdfs.py",
                returncode=1,
            )
        return

    sample_pdf = settings.raw_pdf_dir / "Enhanced_Customer_Guidelines_2024.pdf"
    if not sample_pdf.is_file():
        pytest.skip(f"Seed PDF not found at {sample_pdf} — skipping integration suite")

    try:
        reset_collection()
    except Exception:  # noqa: BLE001
        pass

    # Lazy import: ingestion pipeline pulls in heavy PDF deps (pymupdf4llm)
    # that are absent in the agentic-service container image. With --skip-ingest
    # this branch is never reached inside Docker.
    from agentic_backend.ingestion.pipeline import ingest_document  # noqa: PLC0415

    ingest_document(sample_pdf)


@pytest.fixture(scope="session")
def client() -> httpx.Client:
    """Session-scoped httpx client pointed at the local agentic-service.

    Timeout is generous (300 s) because the executive report pipeline and
    multi-step agentic plans can take over a minute on slower hardware.
    """
    with httpx.Client(base_url=AGENTIC_URL, timeout=300.0) as http_client:
        yield http_client


@pytest.fixture(scope="session")
def chat(client: httpx.Client) -> Callable[..., dict]:
    """Return a callable that POSTs to /chat and returns the parsed JSON response.

    Args:
        question: The user question to send.
        conversation_id: Pass the ID from a previous response to continue
            the same conversation (required for multi-turn tests).
        response_mode: "fast" or "accurate". Omit to use the service default.
    """

    def _chat(
        question: str,
        conversation_id: int | None = None,
        response_mode: str | None = None,
    ) -> dict:
        payload: dict[str, object] = {
            "question": question,
            "user_id": SMOKE_USER,
        }
        if conversation_id is not None:
            payload["conversation_id"] = conversation_id
        if response_mode is not None:
            payload["response_mode"] = response_mode
        resp = client.post("/chat", json=payload)
        resp.raise_for_status()
        return resp.json()

    return _chat
