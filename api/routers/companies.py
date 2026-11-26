from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from api import gold
from api.schemas import CompanyDetail, CompanyOut, FilingOut, FinancialPoint, Page, RiskPoint
from core.db import get_session
from core.models import Company, Filing

router = APIRouter(prefix="/api/companies", tags=["companies"])


def filing_out(f: Filing, company_name: str | None = None) -> FilingOut:
    return FilingOut(
        accession_no=f.accession_no,
        cik=f.cik,
        company_name=company_name,
        form_type=f.form_type,
        filed_at=f.filed_at,
        period_end=f.period_end,
        source_url=f.source_url,
        status=f.status,
        size_bytes=f.size_bytes,
    )


@router.get("", response_model=Page[CompanyOut])
def list_companies(
    q: str | None = None,
    sector: str | None = None,
    limit: int = Query(50, le=500),
    offset: int = 0,
    db: Session = Depends(get_session),
) -> Page[CompanyOut]:
    n_filings = (
        select(func.count()).where(Filing.cik == Company.cik).correlate(Company).scalar_subquery()
    )
    stmt = select(Company, n_filings.label("n")).where(Company.cik != 0)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Company.name.ilike(like), Company.ticker.ilike(like)))
    if sector:
        stmt = stmt.where(Company.sector == sector)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.execute(stmt.order_by(Company.name).limit(limit).offset(offset)).all()
    return Page[CompanyOut](
        items=[
            CompanyOut(
                cik=c.cik,
                name=c.name,
                ticker=c.ticker,
                sic_code=c.sic_code,
                sector=c.sector,
                filings=n,
            )
            for c, n in rows
        ],
        total=total,
    )


@router.get("/{cik}", response_model=CompanyDetail)
def company_detail(cik: int, db: Session = Depends(get_session)) -> CompanyDetail:
    c = db.get(Company, cik)
    if c is None:
        raise HTTPException(404, "company not found")
    filings = list(
        db.scalars(select(Filing).where(Filing.cik == cik).order_by(Filing.filed_at.desc()))
    )
    financials = [
        FinancialPoint(**r)
        for r in gold.safe_query(
            "SELECT fiscal_year, revenue, net_income, operating_cash_flow, source "
            "FROM fct_financials WHERE cik = ? AND fiscal_year > "
            "(SELECT max(fiscal_year) - 10 FROM fct_financials WHERE cik = ?) "
            "ORDER BY fiscal_year, source",
            [cik, cik],
        )
    ]
    risks = [
        RiskPoint(year=r["fiscal_year"], category=r["category"], mentions=int(r["mentions"]))
        for r in gold.safe_query(
            "SELECT fiscal_year, category, sum(mentions) AS mentions FROM fct_risk_mentions "
            "WHERE cik = ? GROUP BY 1, 2 ORDER BY 1, 2",
            [cik],
        )
    ]
    return CompanyDetail(
        company=CompanyOut(
            cik=c.cik,
            name=c.name,
            ticker=c.ticker,
            sic_code=c.sic_code,
            sector=c.sector,
            filings=len(filings),
        ),
        financials=financials,
        risks=risks,
        filings=[filing_out(f, c.name) for f in filings],
    )
