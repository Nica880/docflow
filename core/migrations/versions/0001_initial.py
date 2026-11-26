"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-11-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "companies",
        sa.Column("cik", sa.BigInteger, primary_key=True),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("ticker", sa.String(20)),
        sa.Column("sic_code", sa.String(10)),
        sa.Column("sector", sa.String(100)),
    )
    op.create_table(
        "filings",
        sa.Column("accession_no", sa.String(25), primary_key=True),
        sa.Column("cik", sa.BigInteger, sa.ForeignKey("companies.cik"), nullable=False, index=True),
        sa.Column("form_type", sa.String(20), nullable=False),
        sa.Column("filed_at", sa.Date, nullable=False, index=True),
        sa.Column("period_end", sa.Date),
        sa.Column("source_url", sa.Text, nullable=False),
        sa.Column("checksum", sa.String(64)),
        sa.Column("bronze_key", sa.Text),
        sa.Column("size_bytes", sa.BigInteger),
        sa.Column("ingest_run_id", sa.String(64)),
        sa.Column("status", sa.String(20), nullable=False, server_default="ingested", index=True),
        sa.Column("updated_at", TS, server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "sections",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("accession_no", sa.String(25), sa.ForeignKey("filings.accession_no"), index=True),
        sa.Column("item", sa.String(10), nullable=False),
        sa.Column("title", sa.String(200)),
        sa.Column("text_key", sa.Text, nullable=False),
        sa.Column("char_count", sa.Integer, nullable=False),
        sa.Column("token_estimate", sa.Integer, nullable=False),
        sa.Column("schema_version", sa.String(10), nullable=False, server_default="1"),
        sa.UniqueConstraint("accession_no", "item"),
    )
    op.create_table(
        "section_chunks",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "section_id",
            sa.Integer,
            sa.ForeignKey("sections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("accession_no", sa.String(25), nullable=False, index=True),
        sa.Column("item", sa.String(10), nullable=False),
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("embedding", Vector(768), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.UniqueConstraint("section_id", "chunk_index"),
    )
    op.execute(
        "CREATE INDEX ix_section_chunks_embedding ON section_chunks "
        "USING hnsw (embedding vector_cosine_ops)"
    )
    op.create_table(
        "extractions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("accession_no", sa.String(25), sa.ForeignKey("filings.accession_no"), index=True),
        sa.Column("schema_name", sa.String(50), nullable=False),
        sa.Column("schema_version", sa.String(10), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("prompt_version", sa.String(20), nullable=False),
        sa.Column("payload_json", postgresql.JSONB, nullable=False),
        sa.Column("confidence_json", postgresql.JSONB, nullable=False),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="1"),
        sa.Column("latency_ms", sa.Integer, nullable=False),
        sa.Column("run_tag", sa.String(50)),
        sa.Column("created_at", TS, server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "review_tasks",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "extraction_id",
            sa.Integer,
            sa.ForeignKey("extractions.id", ondelete="CASCADE"),
            index=True,
            nullable=False,
        ),
        sa.Column("field", sa.String(100), nullable=False),
        sa.Column("value", sa.Text),
        sa.Column("confidence", sa.Float, nullable=False),
        sa.Column("reason", sa.Text),
        sa.Column("status", sa.String(20), nullable=False, server_default="open", index=True),
        sa.Column("reviewer_value", sa.Text),
        sa.Column("reviewed_at", TS),
    )
    op.create_table(
        "ground_truth",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("accession_no", sa.String(25), sa.ForeignKey("filings.accession_no"), index=True),
        sa.Column("field", sa.String(100), nullable=False),
        sa.Column("value", sa.Text, nullable=False),
        sa.Column("source", sa.String(30), nullable=False),
        sa.UniqueConstraint("accession_no", "field", "source"),
    )
    op.create_table(
        "pipeline_runs",
        sa.Column("run_id", sa.String(64), primary_key=True),
        sa.Column("dag_id", sa.String(100), nullable=False, index=True),
        sa.Column("started_at", TS, nullable=False),
        sa.Column("finished_at", TS),
        sa.Column("docs_in", sa.Integer, nullable=False, server_default="0"),
        sa.Column("docs_ok", sa.Integer, nullable=False, server_default="0"),
        sa.Column("docs_quarantined", sa.Integer, nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="running"),
    )
    op.create_table(
        "quarantine",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("accession_no", sa.String(25), nullable=False, index=True),
        sa.Column("stage", sa.String(30), nullable=False),
        sa.Column("error", sa.Text, nullable=False),
        sa.Column("payload_key", sa.Text),
        sa.Column("created_at", TS, server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "eval_runs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("prompt_version", sa.String(20), nullable=False),
        sa.Column("n_docs", sa.Integer, nullable=False),
        sa.Column("metrics_json", postgresql.JSONB, nullable=False),
        sa.Column("created_at", TS, server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    for table in (
        "eval_runs",
        "quarantine",
        "pipeline_runs",
        "ground_truth",
        "review_tasks",
        "extractions",
        "section_chunks",
        "sections",
        "filings",
        "companies",
    ):
        op.drop_table(table)
