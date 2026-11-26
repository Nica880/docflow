"""Response/request models of the public HTTP API (the contract the Angular UI consumes)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class Page[T](BaseModel):
    items: list[T]
    total: int


# --- pipeline -----------------------------------------------------------------------------


class PipelineRunOut(BaseModel):
    run_id: str
    dag_id: str
    started_at: datetime
    finished_at: datetime | None
    docs_in: int
    docs_ok: int
    docs_quarantined: int
    status: str
    duration_s: float | None = None


class QuarantineOut(BaseModel):
    id: int
    accession_no: str
    stage: str
    error: str
    created_at: datetime


class ThroughputPoint(BaseModel):
    day: date
    filings: int


class PipelineOverview(BaseModel):
    totals: dict[str, int]
    filings_by_status: dict[str, int]
    queue: dict[str, int] | None = None
    runs: list[PipelineRunOut]
    quarantine: list[QuarantineOut]
    throughput: list[ThroughputPoint]


# --- companies / filings --------------------------------------------------------------------


class CompanyOut(BaseModel):
    cik: int
    name: str
    ticker: str | None
    sic_code: str | None
    sector: str | None
    filings: int = 0


class FinancialPoint(BaseModel):
    fiscal_year: int
    revenue: float | None
    net_income: float | None
    operating_cash_flow: float | None
    source: str  # "llm" | "xbrl"


class RiskPoint(BaseModel):
    year: int
    category: str
    mentions: int


class FilingOut(BaseModel):
    accession_no: str
    cik: int
    company_name: str | None = None
    form_type: str
    filed_at: date
    period_end: date | None
    source_url: str
    status: str
    size_bytes: int | None = None


class CompanyDetail(BaseModel):
    company: CompanyOut
    financials: list[FinancialPoint]
    risks: list[RiskPoint]
    filings: list[FilingOut]


class SectionOut(BaseModel):
    id: int
    item: str
    title: str | None
    char_count: int


class ExtractionOut(BaseModel):
    id: int
    schema_name: str
    schema_version: str
    model: str
    prompt_version: str
    payload: dict[str, Any]
    confidence: dict[str, Any]
    latency_ms: int
    created_at: datetime


class FilingDetail(BaseModel):
    filing: FilingOut
    sections: list[SectionOut]
    extractions: list[ExtractionOut]


class Highlight(BaseModel):
    field: str
    value: str
    snippet: str
    start: int
    end: int


class SectionText(BaseModel):
    accession_no: str
    item: str
    title: str | None
    text: str
    highlights: list[Highlight]


# --- review queue -------------------------------------------------------------------------


class ReviewTaskOut(BaseModel):
    id: int
    extraction_id: int
    accession_no: str
    company_name: str | None
    schema_name: str
    field: str
    value: str | None
    confidence: float
    reason: str | None
    status: str
    reviewer_value: str | None
    reviewed_at: datetime | None
    snippet: str | None = None


class ReviewAction(BaseModel):
    action: Literal["approve", "correct", "reject"]
    value: str | None = None


# --- Q&A agent ----------------------------------------------------------------------------


class Question(BaseModel):
    question: str = Field(min_length=3, max_length=1000)


class Citation(BaseModel):
    accession_no: str
    item: str | None
    company: str | None
    snippet: str


class ToolCallOut(BaseModel):
    tool: str
    input: dict[str, Any]
    output_preview: str


class Answer(BaseModel):
    answer: str
    citations: list[Citation]
    tool_calls: list[ToolCallOut]
    refused: bool = False


# --- evaluation ---------------------------------------------------------------------------


class EvalRunOut(BaseModel):
    id: int
    model: str
    prompt_version: str
    n_docs: int
    metrics: dict[str, Any]
    created_at: datetime


class EvalSummary(BaseModel):
    runs: list[EvalRunOut]
    confidence_threshold: float
