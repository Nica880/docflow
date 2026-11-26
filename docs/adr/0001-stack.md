# ADR-0001: Technology stack

- Status: accepted
- Date: 2026-11-26

## Context
DocFlow must show production-grade Applied AI + Data Engineering work, run entirely on a laptop
with `docker compose`, and cost nothing (no paid APIs, no cloud bills).

## Decision
Python 3.12 (FastAPI, Pydantic v2, SQLAlchemy 2 + Alembic), PostgreSQL 16 + pgvector, MinIO (S3 API),
LocalStack SQS, Apache Airflow 2, dbt-core + dbt-duckdb over Parquet, Ollama for local LLMs and
embeddings, Angular (standalone + signals) for the UI, Terraform for infrastructure, OpenTelemetry +
Prometheus + Grafana for observability, GitHub Actions for CI. uv manages Python dependencies.

## Consequences
- Every cloud dependency has an S3/SQS-compatible local twin, so the same boto3 code path runs
  locally, in CI and on AWS.
- Many moving parts; mitigated by a single `make up && make demo` path and an offline mode
  (recorded EDGAR fixtures + deterministic extractor) that CI uses.
