"""SQLAlchemy 2 ORM models for the operational Postgres database (see docs/PLAN.md §4)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

EMBED_DIM = 768


class Base(DeclarativeBase):
    pass


class Company(Base):
    __tablename__ = "companies"
    cik: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(300))
    ticker: Mapped[str | None] = mapped_column(String(20))
    sic_code: Mapped[str | None] = mapped_column(String(10))
    sector: Mapped[str | None] = mapped_column(String(100))


class Filing(Base):
    __tablename__ = "filings"
    accession_no: Mapped[str] = mapped_column(String(25), primary_key=True)
    cik: Mapped[int] = mapped_column(ForeignKey("companies.cik"), index=True)
    form_type: Mapped[str] = mapped_column(String(20))
    filed_at: Mapped[date] = mapped_column(Date, index=True)
    period_end: Mapped[date | None] = mapped_column(Date)
    source_url: Mapped[str] = mapped_column(Text)
    checksum: Mapped[str | None] = mapped_column(String(64))
    bronze_key: Mapped[str | None] = mapped_column(Text)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    ingest_run_id: Mapped[str | None] = mapped_column(String(64))
    # ingested -> parsed -> extracted | quarantined
    status: Mapped[str] = mapped_column(String(20), default="ingested", index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Section(Base):
    __tablename__ = "sections"
    __table_args__ = (UniqueConstraint("accession_no", "item"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    accession_no: Mapped[str] = mapped_column(ForeignKey("filings.accession_no"), index=True)
    item: Mapped[str] = mapped_column(String(10))
    title: Mapped[str | None] = mapped_column(String(200))
    text_key: Mapped[str] = mapped_column(Text)
    char_count: Mapped[int] = mapped_column(Integer)
    token_estimate: Mapped[int] = mapped_column(Integer)
    schema_version: Mapped[str] = mapped_column(String(10), default="1")


class SectionChunk(Base):
    __tablename__ = "section_chunks"
    __table_args__ = (UniqueConstraint("section_id", "chunk_index"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    section_id: Mapped[int] = mapped_column(ForeignKey("sections.id", ondelete="CASCADE"))
    accession_no: Mapped[str] = mapped_column(String(25), index=True)
    item: Mapped[str] = mapped_column(String(10))
    chunk_index: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[Any] = mapped_column(Vector(EMBED_DIM))
    model: Mapped[str] = mapped_column(String(100))


class Extraction(Base):
    __tablename__ = "extractions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    accession_no: Mapped[str] = mapped_column(ForeignKey("filings.accession_no"), index=True)
    schema_name: Mapped[str] = mapped_column(String(50))
    schema_version: Mapped[str] = mapped_column(String(10))
    model: Mapped[str] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(String(20))
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSONB)
    confidence_json: Mapped[dict[str, Any]] = mapped_column(JSONB)
    attempts: Mapped[int] = mapped_column(Integer, default=1)
    latency_ms: Mapped[int] = mapped_column(Integer)
    run_tag: Mapped[str | None] = mapped_column(String(50))  # "pipeline" | "eval:<id>"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ReviewTask(Base):
    __tablename__ = "review_tasks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    extraction_id: Mapped[int] = mapped_column(
        ForeignKey("extractions.id", ondelete="CASCADE"), index=True
    )
    field: Mapped[str] = mapped_column(String(100))
    value: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float)
    reason: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)
    reviewer_value: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class GroundTruth(Base):
    __tablename__ = "ground_truth"
    __table_args__ = (UniqueConstraint("accession_no", "field", "source"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    accession_no: Mapped[str] = mapped_column(ForeignKey("filings.accession_no"), index=True)
    field: Mapped[str] = mapped_column(String(100))
    value: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(30))  # xbrl | review | hand


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"
    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    dag_id: Mapped[str] = mapped_column(String(100), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    docs_in: Mapped[int] = mapped_column(Integer, default=0)
    docs_ok: Mapped[int] = mapped_column(Integer, default=0)
    docs_quarantined: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="running")


class Quarantine(Base):
    __tablename__ = "quarantine"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    accession_no: Mapped[str] = mapped_column(String(25), index=True)
    stage: Mapped[str] = mapped_column(String(30))
    error: Mapped[str] = mapped_column(Text)
    payload_key: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EvalRun(Base):
    __tablename__ = "eval_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    model: Mapped[str] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(String(20))
    n_docs: Mapped[int] = mapped_column(Integer)
    metrics_json: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
