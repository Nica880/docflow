-- Runs once, on the first start of the postgres container (empty data volume), as the
-- POSTGRES_USER (`docflow`, superuser) connected to POSTGRES_DB (`docflow`).

-- pgvector for section embeddings (Alembic also runs CREATE EXTENSION IF NOT EXISTS).
CREATE EXTENSION IF NOT EXISTS vector;

-- Separate metadata database for Airflow (same server, isolated from app tables).
CREATE DATABASE airflow OWNER docflow;
