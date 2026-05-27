"""Application settings loaded from .env via pydantic-settings."""
from pathlib import Path

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
    embed_model: str = "nomic-embed-text"

    # --- Storage paths ---
    chroma_persist_dir: Path = POC_ROOT / "data" / "chroma_db"
    chroma_collection: str = "policies"
    sqlite_path: Path = POC_ROOT / "data" / "memory.sqlite"
    raw_pdf_dir: Path = POC_ROOT / "data" / "raw"

    # --- FastAPI ---
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # --- Streamlit ---
    ui_api_url: str = "http://localhost:8000"

    # --- RAG tuning ---
    chunk_size: int = 1000
    chunk_overlap: int = 150
    retrieval_k: int = 5

    # --- Observability (Phase 5, Aspire Dashboard via OTLP gRPC) ---
    # Default ON. setup_otel() probes the endpoint at startup and
    # self-disables (logs a warning) if Aspire isn't reachable.
    otel_enabled: bool = True
    otel_endpoint: str = "http://localhost:4317"
    otel_service_name: str = "insurance-rag-poc"
    otel_ui_url: str = "http://localhost:18888"


settings = Settings()
