"""Application settings loaded from .env via pydantic-settings.

Precedence per field: process env > .env file > class default below.

Relative paths in env vars (e.g. `RAW_PDF_DIR=./data/knowledge_base/raw`)
are anchored to POC_ROOT by the field validator at the bottom, so they
behave the same as the absolute defaults regardless of where Python is
launched from.
"""
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

POC_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=POC_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Ollama ---
    ollama_host: str = "http://localhost:11434"
    llm_model: str = "qwen2.5:7b"
    # Phase 11: fast 3B model for the Planner — keeps planning latency
    # low; the heavier 7B is reserved for the actual workers.
    planner_model: str = "qwen2.5:3b"
    embed_model: str = "nomic-embed-text"

    # --- Storage paths ---
    chroma_persist_dir: Path = POC_ROOT / "data" / "chroma_db"
    chroma_collection: str = "policies"
    sqlite_path: Path = POC_ROOT / "data" / "memory.sqlite"
    # Phase 7 audit trail - a separate SQLite file so business memory
    # (memory.sqlite) and audit telemetry don't share a transaction
    # boundary, and the compliance team can copy/rotate this file
    # without touching conversation history.
    audit_sqlite_path: Path = POC_ROOT / "data" / "audit.sqlite"

    # --- Knowledge ingestion (Phase 6) ---
    # data/knowledge_base/raw       <- source PDFs
    # data/knowledge_base/processed <- one .md per document
    # data/knowledge_base/metadata  <- one .json per document + schema.json
    raw_pdf_dir: Path = POC_ROOT / "data" / "knowledge_base" / "raw"
    processed_dir: Path = POC_ROOT / "data" / "knowledge_base" / "processed"
    metadata_dir: Path = POC_ROOT / "data" / "knowledge_base" / "metadata"
    metadata_schema_path: Path = (
        POC_ROOT / "data" / "knowledge_base" / "metadata" / "schema.json"
    )

    # --- FastAPI ---
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # --- Streamlit ---
    ui_api_url: str = "http://localhost:8000"

    # --- RAG tuning ---
    # 1200 / 200 (~17% overlap) is a good default for structured insurance
    # PDFs: roomy enough for a full clause + neighbouring context, precise
    # enough that retrieval doesn't drown in noise.
    chunk_size: int = 1200
    chunk_overlap: int = 200
    retrieval_k: int = 5

    # --- Phase 7: year-aware retrieval ---
    # Knowledge base coverage. The 2023 gap is intentional - the seed
    # PDFs are 2020, 2021, 2022, 2024. The supervisor uses this list
    # to decide whether to route a year-specific question to RAG or
    # to the out_of_year fallback.
    kb_covered_years: list[int] = [2020, 2021, 2022, 2024]

    # --- Phase 8: Talk-to-Data ---
    # Curated KPI CSV. Sparse 'showcase' dataset - one row per
    # (year, month, channel, product_line), cycling through combos,
    # plus two pre-aggregated annual-rollup rows for 2020 and 2024.
    # The Phase 8 executor filters / groups / aggregates this
    # DataFrame at request time.
    kpi_csv_path: Path = (
        POC_ROOT / "data" / "kpi" / "metrics"
        / "insurance_kpis_2020_2024.csv"
    )
    kpi_schema_path: Path = (
        POC_ROOT / "data" / "kpi" / "metrics"
        / "insurance_kpis.schema.json"
    )

    # --- Observability (Phase 5, Aspire Dashboard via OTLP gRPC) ---
    # Default ON. setup_otel() probes the endpoint at startup and
    # self-disables (logs a warning) if Aspire isn't reachable.
    otel_enabled: bool = True
    otel_endpoint: str = "http://localhost:4317"
    otel_service_name: str = "insurance-rag-poc"
    otel_ui_url: str = "http://localhost:18888"

    @field_validator(
        "chroma_persist_dir",
        "sqlite_path",
        "audit_sqlite_path",
        "raw_pdf_dir",
        "processed_dir",
        "metadata_dir",
        "metadata_schema_path",
        mode="before",
    )
    @classmethod
    def _anchor_to_poc_root(cls, v):
        """Anchor any relative path (env or default) to POC_ROOT."""
        if v is None:
            return v
        p = Path(v)
        return p if p.is_absolute() else (POC_ROOT / p).resolve()


settings = Settings()
