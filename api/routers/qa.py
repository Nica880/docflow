from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.agent.agent import Agent
from api.schemas import Answer, EvalRunOut, EvalSummary, Question
from core.config import get_settings
from core.db import get_session
from core.models import EvalRun

qa_router = APIRouter(prefix="/api/qa", tags=["qa"])
eval_router = APIRouter(prefix="/api/eval", tags=["eval"])


@qa_router.post("", response_model=Answer)
async def ask(q: Question) -> Answer:
    return await run_in_threadpool(Agent().ask, q.question)


@eval_router.get("", response_model=EvalSummary)
def evals(db: Session = Depends(get_session)) -> EvalSummary:
    runs = db.scalars(select(EvalRun).order_by(EvalRun.created_at.desc()).limit(50))
    return EvalSummary(
        runs=[
            EvalRunOut(
                id=r.id,
                model=r.model,
                prompt_version=r.prompt_version,
                n_docs=r.n_docs,
                metrics=r.metrics_json,
                created_at=r.created_at,
            )
            for r in runs
        ],
        confidence_threshold=get_settings().confidence_threshold,
    )
