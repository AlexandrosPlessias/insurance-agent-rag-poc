"""Application settings loaded from .env via pydantic-settings.

Precedence per field: process env > .env file > class default below.

Relative paths in env vars (e.g. `RAW_PDF_DIR=./data/knowledge_base/raw`)
are anchored to POC_ROOT by the field validator at the bottom, so they
behave the same as the absolute defaults regardless of where Python is
launched from.
"""
import logging
from pathlib import Path

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_log = logging.getLogger(__name__)

POC_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=POC_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Ollama ---
    ollama_host: str = "http://ollama:11434"
    llm_model: str = "qwen2.5:7b"
    # fast 3B model for the Planner — keeps planning latency
    # low; the heavier 7B is reserved for the actual workers.
    planner_model: str = "qwen2.5:3b"
    embed_model: str = "nomic-embed-text"

    # --- Storage paths ---
    chroma_collection: str = "policies"
    sqlite_path: Path = POC_ROOT / "data" / "memory.sqlite"
    # Separate SQLite file so business memory
    # (memory.sqlite) and audit telemetry don't share a transaction
    # boundary, and the compliance team can copy/rotate this file
    # without touching conversation history.
    audit_sqlite_path: Path = POC_ROOT / "data" / "audit.sqlite"

    # --- Knowledge ingestion ---
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

    # --- RAG tuning ---
    # 1200 / 200 (~17% overlap) is a good default for structured insurance
    # PDFs: roomy enough for a full clause + neighbouring context, precise
    # enough that retrieval doesn't drown in noise.
    chunk_size: int = 1200
    chunk_overlap: int = 200
    retrieval_k: int = 5

    # --- year-aware retrieval ---
    # Knowledge base coverage. The 2023 gap is intentional - the seed
    # PDFs are 2020, 2021, 2022, 2024. The supervisor uses this list
    # to decide whether to route a year-specific question to RAG or
    # to the out_of_year fallback.
    kb_covered_years: list[int] = [2020, 2021, 2022, 2024]

    # --- Talk-to-Data ---
    # Curated KPI CSV. Sparse 'showcase' dataset - one row per
    # (year, month, channel, product_line), cycling through combos,
    # plus two pre-aggregated annual-rollup rows for 2020 and 2024.
    # The executor filters / groups / aggregates this
    # DataFrame at request time.
    kpi_csv_path: Path = (
        POC_ROOT / "data" / "kpi" / "metrics"
        / "insurance_kpis_2020_2024.csv"
    )
    kpi_schema_path: Path = (
        POC_ROOT / "data" / "kpi" / "metrics"
        / "insurance_kpis.schema.json"
    )

    # --- HITL approval gates ---
    # Override via APPROVAL_HMAC_SECRET env var before any production deployment.
    approval_hmac_secret: str = "dev-insecure-secret-change-me"
    # KPI threshold above which a computed figure triggers the approval gate.
    approvals_kpi_threshold: float = 1_000_000.0
    # Telegram bot (optional — leave blank to use UI-only channel).
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # --- Container orchestration (Phase 14) ---
    chroma_host: str = "chromadb"
    chroma_port: int = 8000   # internal Docker port; host-side is mapped to 8005
    agentic_service_url: str = "http://agentic-service:8002"
    rag_service_url: str = "http://rag-service:8003"
    voice_service_url: str = "http://voice-service:8001"
    ingestion_service_url: str = "http://ingestion-service:8004"
    # Set to true to force a full ChromaDB wipe + re-ingest on next startup.
    # Reset to false (or remove) after the re-index completes.
    force_reingest: bool = False

    # --- Voice I/O (Phase 13) ---
    voice_enabled: bool = True
    voice_stt_model: str = "medium"
    voice_tts_voice: str = "en_US-lessac-medium"
    voice_tts_voice_el: str = "el_GR-rapunzelina-low"
    voice_models_dir: Path = POC_ROOT / "voice" / "piper_voices"
    # When true, raw audio blobs are persisted alongside the audit log so
    # compliance teams can replay STT decisions.  Blobs land at:
    # <audit_audio_dir>/<sha256>.wav
    audit_retain_audio: bool = False
    audit_audio_dir: Path = POC_ROOT / "data" / "audit_audio"

    # --- Observability ---
    # Default ON. setup_otel() probes the endpoint at startup and
    # self-disables (logs a warning) if Aspire isn't reachable.
    otel_enabled: bool = True
    otel_endpoint: str = "http://aspire:18889"
    otel_service_name: str = "rag-poc"
    otel_ui_url: str = "http://localhost:18888"

    @model_validator(mode="after")
    def _warn_insecure_defaults(self) -> "Settings":
        if self.approval_hmac_secret == "dev-insecure-secret-change-me":
            _log.warning(
                "SECURITY: approval_hmac_secret is using the insecure default. "
                "Set APPROVAL_HMAC_SECRET in your .env before any non-local use."
            )
        return self

    @field_validator(
        "sqlite_path",
        "audit_sqlite_path",
        "raw_pdf_dir",
        "processed_dir",
        "metadata_dir",
        "metadata_schema_path",
        "audit_audio_dir",
        "voice_models_dir",
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
