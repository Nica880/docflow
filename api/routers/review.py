from __future__ import annotations

import re
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.schemas import Page, ReviewAction, ReviewTaskOut
from core.db import get_session
from core.models import Company, Extraction, Filing, GroundTruth, ReviewTask
from processing.schemas import UNIT_MULTIPLIER

router = APIRouter(prefix="/api/review", tags=["review"])

FIN_FIELDS = ("revenue", "net_income", "operating_cash_flow", "fiscal_year")


def snippet_for(ext: Extraction, field: str) -> str | None:
    p = ext.payload_json
    m = re.fullmatch(r"risks\[(\d+)\]\.category", field)
    if m:
        risks = p.get("risks", [])
        i = int(m.group(1))
        return risks[i].get("snippet") if i < len(risks) else None
    return p.get(f"{field}_snippet")


def to_out(t: ReviewTask, ext: Extraction, company: str | None) -> ReviewTaskOut:
    return ReviewTaskOut(
        id=t.id,
        extraction_id=t.extraction_id,
        accession_no=ext.accession_no,
        company_name=company,
        schema_name=ext.schema_name,
        field=t.field,
        value=t.value,
        confidence=t.confidence,
        reason=t.reason,
        status=t.status,
        reviewer_value=t.reviewer_value,
        reviewed_at=t.reviewed_at,
        snippet=snippet_for(ext, t.field),
    )


@router.get("", response_model=Page[ReviewTaskOut])
def list_tasks(
    status: str = "open",
    limit: int = Query(50, le=500),
    offset: int = 0,
    db: Session = Depends(get_session),
) -> Page[ReviewTaskOut]:
    stmt = (
        select(ReviewTask, Extraction, Company.name)
        .join(Extraction, Extraction.id == ReviewTask.extraction_id)
        .join(Filing, Filing.accession_no == Extraction.accession_no)
        .join(Company, Company.cik == Filing.cik)
        .where(ReviewTask.status == status)
    )
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.execute(
        stmt.order_by(ReviewTask.confidence, ReviewTask.id).limit(limit).offset(offset)
    ).all()
    return Page[ReviewTaskOut](items=[to_out(t, e, c) for t, e, c in rows], total=total)


def ground_truth_value(ext: Extraction, field: str, value: str) -> str | None:
    """Reviewer values are entered in the extraction's reported units; GT is stored in USD."""
    if ext.schema_name != "FinancialHighlights" or field not in FIN_FIELDS:
        return None
    try:
        num = float(value.replace(",", ""))
    except ValueError as exc:
        raise HTTPException(422, f"'{value}' is not a number") from exc
    if field == "fiscal_year":
        return repr(float(int(num)))
    return repr(num * UNIT_MULTIPLIER.get(ext.payload_json.get("units", "millions"), 1e6))


@router.post("/{task_id}", response_model=ReviewTaskOut)
def act(task_id: int, action: ReviewAction, db: Session = Depends(get_session)) -> ReviewTaskOut:
    task = db.get(ReviewTask, task_id)
    if task is None:
        raise HTTPException(404, "review task not found")
    ext = db.get(Extraction, task.extraction_id)
    assert ext is not None
    if action.action == "correct" and not action.value:
        raise HTTPException(422, "a corrected value is required")
    final = action.value if action.action == "correct" else task.value
    task.status = {"approve": "approved", "correct": "corrected", "reject": "rejected"}[
        action.action
    ]
    task.reviewer_value = final if action.action != "reject" else None
    task.reviewed_at = datetime.now(UTC)
    if action.action != "reject" and final is not None:
        gt = ground_truth_value(ext, task.field, final)
        if gt is not None:
            existing = db.scalar(
                select(GroundTruth).where(
                    GroundTruth.accession_no == ext.accession_no,
                    GroundTruth.field == task.field,
                    GroundTruth.source == "review",
                )
            )
            if existing:
                existing.value = gt
            else:
                db.add(
                    GroundTruth(
                        accession_no=ext.accession_no, field=task.field, value=gt, source="review"
                    )
                )
    db.flush()
    filing = db.get(Filing, ext.accession_no)
    company = db.get(Company, filing.cik) if filing else None
    return to_out(task, ext, company.name if company else None)
