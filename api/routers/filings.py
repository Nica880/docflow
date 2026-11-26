from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.routers.companies import filing_out
from api.schemas import (
    ExtractionOut,
    FilingDetail,
    FilingOut,
    Highlight,
    Page,
    SectionOut,
    SectionText,
)
from core.db import get_session
from core.models import Company, Extraction, Filing, Section
from processing.context import SOURCE_ITEMS
from processing.silver import load_section_text

router = APIRouter(prefix="/api/filings", tags=["filings"])


@router.get("", response_model=Page[FilingOut])
def list_filings(
    cik: int | None = None,
    form_type: str | None = None,
    status: str | None = None,
    limit: int = Query(50, le=500),
    offset: int = 0,
    db: Session = Depends(get_session),
) -> Page[FilingOut]:
    stmt = select(Filing, Company.name).join(Company, Company.cik == Filing.cik)
    if cik is not None:
        stmt = stmt.where(Filing.cik == cik)
    if form_type:
        stmt = stmt.where(Filing.form_type == form_type)
    if status:
        stmt = stmt.where(Filing.status == status)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.execute(stmt.order_by(Filing.filed_at.desc()).limit(limit).offset(offset)).all()
    return Page[FilingOut](items=[filing_out(f, name) for f, name in rows], total=total)


def _extraction_out(e: Extraction) -> ExtractionOut:
    return ExtractionOut(
        id=e.id,
        schema_name=e.schema_name,
        schema_version=e.schema_version,
        model=e.model,
        prompt_version=e.prompt_version,
        payload=e.payload_json,
        confidence=e.confidence_json,
        latency_ms=e.latency_ms,
        created_at=e.created_at,
    )


def latest_pipeline_extractions(db: Session, accession_no: str) -> list[Extraction]:
    rows = db.scalars(
        select(Extraction)
        .where(Extraction.accession_no == accession_no, Extraction.run_tag == "pipeline")
        .order_by(Extraction.created_at.desc())
    )
    latest: dict[str, Extraction] = {}
    for e in rows:
        latest.setdefault(e.schema_name, e)
    return list(latest.values())


@router.get("/{accession_no}", response_model=FilingDetail)
def filing_detail(accession_no: str, db: Session = Depends(get_session)) -> FilingDetail:
    f = db.get(Filing, accession_no)
    if f is None:
        raise HTTPException(404, "filing not found")
    company = db.get(Company, f.cik)
    sections = db.scalars(
        select(Section).where(Section.accession_no == accession_no).order_by(Section.id)
    )
    return FilingDetail(
        filing=filing_out(f, company.name if company else None),
        sections=[
            SectionOut(id=s.id, item=s.item, title=s.title, char_count=s.char_count)
            for s in sections
        ],
        extractions=[_extraction_out(e) for e in latest_pipeline_extractions(db, accession_no)],
    )


def locate(text: str, snippet: str) -> tuple[int, int] | None:
    """Find a (possibly whitespace-normalised) snippet in the original text."""
    idx = text.find(snippet)
    if idx >= 0:
        return idx, idx + len(snippet)
    words = re.findall(r"\S+", snippet)
    for n in (len(words), 12, 6):
        if n == 0 or n > len(words):
            continue
        pattern = r"\s+".join(re.escape(w) for w in words[:n])
        m = re.search(pattern, text)
        if m:
            return m.start(), m.end()
    return None


def highlights_for(item: str, text: str, extractions: list[Extraction]) -> list[Highlight]:
    out: list[Highlight] = []
    for e in extractions:
        if item not in SOURCE_ITEMS.get(e.schema_name, ()):
            continue
        p = e.payload_json
        pairs: list[tuple[str, str, str]] = []
        if e.schema_name == "FinancialHighlights":
            for field in ("revenue", "net_income", "operating_cash_flow"):
                if p.get(f"{field}_snippet") and p.get(field) is not None:
                    pairs.append(
                        (field, f"{p[field]:,} {p.get('units', '')}".strip(), p[f"{field}_snippet"])
                    )
        elif e.schema_name == "RiskFactors":
            for r in p.get("risks", []):
                pairs.append((f"risk:{r['category']}", r["summary"], r["snippet"]))
        for field, value, snippet in pairs:
            span = locate(text, snippet)
            if span:
                out.append(
                    Highlight(field=field, value=value, snippet=snippet, start=span[0], end=span[1])
                )
    out.sort(key=lambda h: h.start)
    dedup: list[Highlight] = []
    for h in out:
        if not dedup or h.start >= dedup[-1].end:
            dedup.append(h)
    return dedup


@router.get("/{accession_no}/sections/{item}", response_model=SectionText)
def section_text(accession_no: str, item: str, db: Session = Depends(get_session)) -> SectionText:
    try:
        text, title = load_section_text(accession_no, item.upper())
    except KeyError as exc:
        raise HTTPException(404, "section not found") from exc
    exts = latest_pipeline_extractions(db, accession_no)
    return SectionText(
        accession_no=accession_no,
        item=item.upper(),
        title=title,
        text=text,
        highlights=highlights_for(item.upper(), text, exts),
    )
