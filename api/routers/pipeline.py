from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.schemas import PipelineOverview, PipelineRunOut, QuarantineOut, ThroughputPoint
from core.db import get_session
from core.models import (
    Company,
    Extraction,
    Filing,
    PipelineRun,
    Quarantine,
    ReviewTask,
    Section,
    SectionChunk,
)

router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])


def _count(db: Session, stmt: object) -> int:
    return int(db.scalar(stmt) or 0)  # type: ignore[call-overload]


@router.get("/overview", response_model=PipelineOverview)
def overview(db: Session = Depends(get_session)) -> PipelineOverview:
    real = Filing.form_type != "INVOICE"
    totals = {
        "companies": _count(db, select(func.count()).select_from(Company).where(Company.cik != 0)),
        "filings": _count(db, select(func.count()).select_from(Filing).where(real)),
        "sections": _count(db, select(func.count()).select_from(Section)),
        "chunks": _count(db, select(func.count()).select_from(SectionChunk)),
        "extractions": _count(
            db, select(func.count()).select_from(Extraction).where(Extraction.run_tag == "pipeline")
        ),
        "open_reviews": _count(
            db, select(func.count()).select_from(ReviewTask).where(ReviewTask.status == "open")
        ),
        "quarantined": _count(db, select(func.count()).select_from(Quarantine)),
    }
    by_status = {
        status: n
        for status, n in db.execute(
            select(Filing.status, func.count()).where(real).group_by(Filing.status)
        ).all()
    }
    runs = [
        PipelineRunOut(
            run_id=r.run_id,
            dag_id=r.dag_id,
            started_at=r.started_at,
            finished_at=r.finished_at,
            docs_in=r.docs_in,
            docs_ok=r.docs_ok,
            docs_quarantined=r.docs_quarantined,
            status=r.status,
            duration_s=(r.finished_at - r.started_at).total_seconds() if r.finished_at else None,
        )
        for r in db.scalars(select(PipelineRun).order_by(PipelineRun.started_at.desc()).limit(25))
    ]
    quarantine = [
        QuarantineOut(
            id=q.id,
            accession_no=q.accession_no,
            stage=q.stage,
            error=q.error[:500],
            created_at=q.created_at,
        )
        for q in db.scalars(select(Quarantine).order_by(Quarantine.created_at.desc()).limit(25))
    ]
    since = datetime.now(UTC) - timedelta(days=30)
    day = func.date(PipelineRun.started_at)
    throughput = [
        ThroughputPoint(day=d, filings=int(n))
        for d, n in db.execute(
            select(day, func.count(Filing.accession_no))
            .join(PipelineRun, PipelineRun.run_id == Filing.ingest_run_id)
            .where(PipelineRun.started_at >= since, real)
            .group_by(day)
            .order_by(day)
        ).all()
    ]
    queue_depth = None
    try:
        from core import queue

        queue_depth = queue.depth()
    except Exception:  # noqa: S110 - the queue is optional for the overview
        pass
    return PipelineOverview(
        totals=totals,
        filings_by_status=by_status,
        queue=queue_depth,
        runs=runs,
        quarantine=quarantine,
        throughput=throughput,
    )
