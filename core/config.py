"""Central configuration, read from environment variables (and `.env` when present)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- SEC EDGAR -----------------------------------------------------------------------
    # SEC fair-access policy: descriptive User-Agent with a contact email, max 10 req/s.
    sec_user_agent: str = Field(default="", description="e.g. 'DocFlow research you@example.com'")
    sec_max_rps: float = 8.0
    sec_base_www: str = "https://www.sec.gov"
    sec_base_data: str = "https://data.sec.gov"
    # When set, EDGAR HTTP calls are served from recorded fixtures (offline CI / demos).
    edgar_fixtures_dir: Path | None = None

    # --- Postgres --------------------------------------------------------------------------
    database_url: str = "postgresql+psycopg://docflow:docflow@localhost:5432/docflow"

    # --- Object storage (MinIO / S3) -------------------------------------------------------
    s3_endpoint_url: str | None = "http://localhost:9000"
    s3_access_key: str = "docflow"
    s3_secret_key: str = "docflow-secret"  # noqa: S105 - local dev default
    s3_region: str = "us-east-1"
    bronze_bucket: str = "docflow-bronze"
    silver_bucket: str = "docflow-silver"

    # --- Queue (LocalStack SQS) -------------------------------------------------------------
    sqs_endpoint_url: str | None = "http://localhost:4566"
    sqs_queue_name: str = "docflow-extract"
    aws_access_key_id: str = "test"
    aws_secret_access_key: str = "test"  # noqa: S105 - LocalStack default

    # --- LLM (Ollama) ----------------------------------------------------------------------
    llm_provider: str = "ollama"  # "ollama" | "fake" (deterministic, for CI)
    ollama_base_url: str = "http://localhost:11434"
    llm_model: str = "qwen2.5:7b-instruct"
    llm_compare_model: str = "llama3.1:8b"
    embed_model: str = "nomic-embed-text"
    embed_dim: int = 768
    llm_num_ctx: int = 8192
    llm_timeout_s: float = 300.0
    prompt_version: str = "v1"
    confidence_threshold: float = 0.7

    # --- Warehouse -------------------------------------------------------------------------
    warehouse_dir: Path = Path("data/warehouse")
    lake_dir: Path = Path("data/lake")  # Parquet exports read by dbt sources
    dbt_project_dir: Path = Path("warehouse")

    # --- API -------------------------------------------------------------------------------
    api_cors_origins: list[str] = ["http://localhost:4200", "http://localhost:8080"]
    agent_max_steps: int = 6
    sql_row_limit: int = 200
    sql_timeout_s: float = 5.0

    # --- Demo / small mode -----------------------------------------------------------------
    demo_years: int = 10
    demo_max_filings: int = 500
    demo_extract_filings: int = 12
    demo_embed_latest_only: bool = True
    embed_max_chunks_per_section: int = 40

    # --- Observability ---------------------------------------------------------------------
    otel_exporter_otlp_endpoint: str | None = None
    service_name: str = "docflow"
    log_level: str = "INFO"

    @field_validator("edgar_fixtures_dir", "otel_exporter_otlp_endpoint", mode="before")
    @classmethod
    def _empty_is_none(cls, v: object) -> object:
        return None if v == "" else v

    @property
    def gold_db_path(self) -> Path:
        return self.warehouse_dir / "gold.duckdb"


@lru_cache
def get_settings() -> Settings:
    return Settings()
